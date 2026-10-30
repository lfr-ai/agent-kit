# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Collect deliberate-shortcut marker comments into a Markdown debt ledger.

A debt marker is a comment such as '# DEBT(owner=@orders-team,
revisit=2026-09-30): cache is per-process; replace when we scale out'. The
collector scans explicit paths, never executes or imports them, writes a
deterministic ledger table, and reports malformed or expired markers as
``path:line: message`` findings with exit status 1.
"""

import argparse
from dataclasses import dataclass
import datetime as dt
from enum import StrEnum
import fnmatch
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

_DEFAULT_MARKERS = ("DEBT", "SHORTCUT")
_DEFAULT_EXTENSIONS = (
    ".bicep",
    ".c",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".html",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".md",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".tf",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
)
_DEFAULT_EXCLUDES = (
    ".git",
    ".hg",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
)
_COMMENT_LEADER = r"(?:#|//|/\*|\*|--|<!--|;|%|\bREM\b)"
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EXIT_USAGE = 2
_SELF_TEST_AS_OF = dt.date(2026, 6, 1)
_SELF_TEST_MARKER_LINES = (2, 3, 4)


@dataclass(frozen=True, kw_only=True, slots=True)
class Entry:
    """One collected debt marker.

    Args:
        path: File that holds the marker.
        line: One-based line number.
        marker: Marker keyword that matched.
        owner: Declared owner, or an empty string.
        revisit: Declared revisit date or trigger, or an empty string.
        reason: Free-text reason after the colon.
    """

    path: Path
    line: int
    marker: str
    owner: str
    revisit: str
    reason: str


@dataclass(frozen=True, kw_only=True, slots=True)
class Options:
    """Scan configuration.

    Args:
        markers: Marker keywords, matched as whole words after a comment leader.
        extensions: File suffixes to scan; empty means every file.
        excludes: Glob patterns matched against each path part to skip.
        as_of: Date used to flag expired revisit dates; None disables expiry.
        require_owner: Report markers that declare no owner.
    """

    markers: tuple[str, ...] = _DEFAULT_MARKERS
    extensions: tuple[str, ...] = _DEFAULT_EXTENSIONS
    excludes: tuple[str, ...] = _DEFAULT_EXCLUDES
    as_of: dt.date | None = None
    require_owner: bool = False


def _pattern(markers: tuple[str, ...]) -> re.Pattern[str]:
    """Compile the marker pattern: leader, keyword, optional metadata, colon."""
    names = "|".join(map(re.escape, markers))
    return re.compile(
        _COMMENT_LEADER
        + r"\s*(?P<marker>"
        + names
        + r")\b\s*(?:\((?P<meta>[^)]*)\))?\s*(?P<colon>:)?\s*(?P<reason>.*)$"
    )


def _metadata(raw: str) -> dict[str, str]:
    """Parse ``key=value`` pairs separated by commas or semicolons."""
    pairs: dict[str, str] = {}
    for item in re.split(r"[,;]", raw):
        key, separator, value = item.partition("=")
        if separator:
            pairs[key.strip().casefold()] = value.strip()
    return pairs


def _clean_reason(text: str) -> str:
    """Strip trailing block-comment closers from a reason."""
    return re.sub(r"\s*(?:\*/|--!?>)\s*$", "", text).strip()


def scan_text(path: Path, text: str, markers: tuple[str, ...]) -> list[Entry]:
    """Collect markers from one file's text.

    Args:
        path: File path recorded in each entry.
        text: File contents.
        markers: Marker keywords to match.

    Returns:
        Entries in line order.
    """
    pattern = _pattern(markers)
    entries: list[Entry] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = pattern.search(line)
        if not match:
            continue
        meta = _metadata(match.group("meta") or "")
        reason = _clean_reason(match.group("reason")) if match.group("colon") else ""
        entries.append(
            Entry(
                path=path,
                line=number,
                marker=match.group("marker"),
                owner=meta.get("owner", ""),
                revisit=meta.get("revisit", ""),
                reason=reason,
            )
        )
    return entries


def _excluded(path: Path, excludes: tuple[str, ...]) -> bool:
    """Return whether any path part matches an exclude glob."""
    return any(
        fnmatch.fnmatch(part, pattern) for part in path.parts for pattern in excludes
    )


def discover(paths: list[Path], options: Options) -> list[Path]:
    """Expand explicit files and directories into scan targets.

    Explicit files are always scanned; directory members are filtered by
    extension and by exclude globs matched against their relative path parts.

    Args:
        paths: Files or directories given on the command line.
        options: Extension and exclude configuration.

    Returns:
        Sorted, de-duplicated file paths.
    """
    files: set[Path] = set()
    for path in paths:
        if path.is_file():
            files.add(path)
            continue
        for candidate in sorted(path.rglob("*")):
            if (
                candidate.is_file()
                and not candidate.is_symlink()
                and not _excluded(candidate.relative_to(path), options.excludes)
                and (
                    not options.extensions
                    or candidate.suffix.casefold() in options.extensions
                )
            ):
                files.add(candidate)
    return sorted(files)


def problems(entries: list[Entry], options: Options) -> list[str]:
    """Report malformed, ownerless or expired markers.

    Args:
        entries: Collected markers.
        options: Expiry date and ownership requirement.

    Returns:
        Deterministic ``path:line: message`` findings.
    """
    findings: list[str] = []
    for entry in entries:
        where = f"{entry.path.as_posix()}:{entry.line}"
        if not entry.reason:
            findings.append(f"{where}: {entry.marker} marker has no ': reason'")
        if options.require_owner and not entry.owner:
            findings.append(f"{where}: {entry.marker} marker has no owner")
        date_problem = _revisit_problem(entry, where, options.as_of)
        if date_problem is not None:
            findings.append(date_problem)
    return findings


def _revisit_problem(entry: Entry, where: str, as_of: dt.date | None) -> str | None:
    """Report an invalid or expired ISO revisit date, if any."""
    if not _ISO_DATE.match(entry.revisit):
        return None
    try:
        revisit = dt.date.fromisoformat(entry.revisit)
    except ValueError:
        return f"{where}: invalid revisit date '{entry.revisit}'"
    if as_of is not None and revisit < as_of:
        return (
            f"{where}: {entry.marker} expired on {entry.revisit}"
            f" (as of {as_of.isoformat()})"
        )
    return None


def _cell(value: str) -> str:
    """Escape a value for a Markdown table cell."""
    return value.replace("|", r"\|") or "-"


def render_ledger(entries: list[Entry], *, title: str) -> str:
    """Render entries as a Markdown ledger with per-marker counts.

    Args:
        entries: Collected markers.
        title: Level-one heading text.

    Returns:
        Markdown text ending with a newline.
    """
    lines = [f"# {title}", ""]
    if not entries:
        lines.extend(["No debt markers found.", ""])
        return "\n".join(lines)
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.marker] = counts.get(entry.marker, 0) + 1
    summary = ", ".join(f"{name}: {counts[name]}" for name in sorted(counts))
    lines.extend(
        [
            f"Total: {len(entries)} ({summary})",
            "",
            "| Location | Marker | Owner | Revisit | Reason |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    lines.extend(
        f"| `{entry.path.as_posix()}:{entry.line}` | {entry.marker} | "
        f"{_cell(entry.owner)} | {_cell(entry.revisit)} | {_cell(entry.reason)} |"
        for entry in entries
    )
    lines.append("")
    return "\n".join(lines)


def collect(paths: list[Path], options: Options) -> list[Entry]:
    """Scan explicit paths and return every marker in path and line order.

    Args:
        paths: Files or directories to scan.
        options: Scan configuration.

    Returns:
        Collected entries.

    Raises:
        OSError: A target cannot be read.
    """
    entries: list[Entry] = []
    for path in discover(paths, options):
        text = path.read_text(encoding="utf-8", errors="replace")
        entries.extend(scan_text(path, text, options.markers))
    return entries


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    MISSING_FINDING = "missing finding: {expected}"
    INVALID_DATE_ACCEPTED = "invalid date must be reported"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(self, issue: SelfTestIssue, *, expected: str | None = None) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
            expected: Observed expected for the failing case.
        """
        super().__init__(issue.value.format(expected=expected))


def self_test() -> None:
    """Exercise collection, rendering and every finding type.

    Raises:
        AssertionError: Behavior differs from the documented contract.
        SelfTestError: A date or finding check fails.
    """
    with TemporaryDirectory(prefix="debt-ledger-") as raw:
        root = Path(raw)
        (root / "src").mkdir()
        (root / "src" / "cache.py").write_text(
            "DEBT_LIMIT = 3\n"
            "# DEBT(owner=@orders-team, revisit=2026-01-31): per-process cache\n"
            "# SHORTCUT: retry once | then give up\n"
            "# DEBT(revisit=2026-13-40)\n",
            encoding="utf-8",
        )
        (root / "node_modules").mkdir()
        (root / "node_modules" / "skip.js").write_text(
            "// DEBT: ignored\n", encoding="utf-8"
        )
        options = Options(as_of=_SELF_TEST_AS_OF, require_owner=True)
        entries = collect([root], options)
        if tuple(entry.line for entry in entries) != _SELF_TEST_MARKER_LINES:
            raise AssertionError(entries)
        ledger = render_ledger(entries, title="Debt ledger")
        if r"retry once \| then give up" not in ledger or "@orders-team" not in ledger:
            raise AssertionError(ledger)
        found = " ".join(problems(entries, options))
        for expected in ("expired on 2026-01-31", "has no owner", "no ': reason'"):
            if expected not in found:
                raise SelfTestError(SelfTestIssue.MISSING_FINDING, expected=expected)
        if "invalid revisit date" not in found:
            raise SelfTestError(SelfTestIssue.INVALID_DATE_ACCEPTED)


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--marker", action="append", default=[])
    parser.add_argument(
        "--ext",
        action="append",
        default=[],
        help="file suffix to scan, e.g. '.py' (repeatable; replaces defaults)",
    )
    parser.add_argument("--all-files", action="store_true")
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--as-of", type=dt.date.fromisoformat, default=None)
    parser.add_argument("--require-owner", action="store_true")
    parser.add_argument("--title", default="Debt ledger")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--self-test", action="store_true")
    return parser


def _options(args: argparse.Namespace) -> Options:
    """Build scan options from parsed arguments and defaults."""
    extensions = tuple(item.casefold() for item in args.ext) or _DEFAULT_EXTENSIONS
    return Options(
        markers=tuple(args.marker) or _DEFAULT_MARKERS,
        extensions=() if args.all_files else extensions,
        excludes=tuple(args.exclude) or _DEFAULT_EXCLUDES,
        as_of=args.as_of,
        require_owner=args.require_owner,
    )


def _write_ledger(ledger: str, output: Path | None) -> None:
    """Write the ledger to ``output`` or standard output."""
    if output is None:
        sys.stdout.write(ledger)
        return
    output.write_text(ledger, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    """Write the ledger and report findings.

    Args:
        argv: Command-line arguments; ``sys.argv`` when omitted.

    Returns:
        0 when every marker is well formed, 1 on findings, 2 on unusable input.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        sys.stdout.write("collect_debt_markers self-test passed.\n")
        return 0
    if not args.paths:
        parser.print_usage(sys.stderr)
        return _EXIT_USAGE
    missing = [path for path in args.paths if not path.exists()]
    if missing:
        sys.stderr.write(f"path not found: {missing[0]}\n")
        return _EXIT_USAGE
    options = _options(args)
    try:
        entries = collect(args.paths, options)
    except OSError as error:
        sys.stderr.write(f"cannot read target: {error}\n")
        return _EXIT_USAGE
    _write_ledger(render_ledger(entries, title=args.title), args.output)
    findings = problems(entries, options)
    for finding in findings:
        sys.stderr.write(f"{finding}\n")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
