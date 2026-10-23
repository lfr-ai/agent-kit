"""Flag stale dated memory or decision entries and links to missing local files.

An entry is a Markdown heading that contains an ISO date such as
``## 2026-03-14 Retry policy for invoice exports``. The entry is stale when its
effective date is older than ``--max-age-days`` before ``--today``. A line inside
the entry such as ``Last verified: 2026-09-01`` refreshes the effective date.
Entries marked ``Status: superseded`` are historical and are not aged, but their
links are still checked. Local links must resolve to an existing file inside
``--root``; web links and in-page anchors are not fetched.

Findings are printed as ``path:line: message``. Exit status: 0 when clean, 1 on
findings, 2 when inputs cannot be read.
"""

import argparse
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path, PureWindowsPath
import re
import sys
from urllib.parse import unquote

_HEADING = re.compile(r"^#{1,6}\s+(?P<title>.*)$")
_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_VERIFIED = re.compile(
    r"^\s*(?:[-*]\s*)?\**(?:last\s+verified|verified|reviewed)\**\s*:\**\s*"
    r"(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_SUPERSEDED = re.compile(
    r"^\s*(?:[-*]\s*)?\**status\**\s*:\**\s*superseded", re.IGNORECASE
)
_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_FENCE = re.compile(r"^\s*(```|~~~)")
_EXTERNAL = ("http://", "https://", "mailto:", "#")
_EXIT_USAGE = 2
_DEFAULT_MAX_AGE_DAYS = 180
_SELF_TEST_TODAY = date(2026, 6, 30)
_SELF_TEST_MAX_AGE_DAYS = 90


@dataclass(frozen=True, kw_only=True, slots=True)
class Entry:
    """One dated heading and the lines that belong to it.

    Attributes:
        line: The 1-based heading line.
        title: The heading text.
        dated: The date written in the heading.
        verified: Later verification dates found in the body.
        superseded: Whether the body marks the entry as superseded.
    """

    line: int
    title: str
    dated: date
    verified: tuple[date, ...]
    superseded: bool

    @property
    def effective(self) -> date:
        """Return the most recent heading or verification date."""
        return max((self.dated, *self.verified))


def _parse_date(text: str) -> date | None:
    """Parse an ISO calendar date, returning None when it is not a real date."""
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _content_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield numbered lines that are outside fenced code blocks."""
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = _FENCE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence is None:
            yield number, line


def _headings(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Return ``(index, title)`` pairs for every heading in ``lines``."""
    headings: list[tuple[int, str]] = []
    for index, (_, line) in enumerate(lines):
        heading = _HEADING.match(line)
        if heading:
            headings.append((index, heading.group("title").strip()))
    return headings


def _entry_body(
    body: list[tuple[int, str]], problems: list[tuple[int, str]]
) -> tuple[tuple[date, ...], bool]:
    """Collect verification dates and the superseded flag from an entry body.

    Args:
        body: Numbered lines between the entry heading and the next heading.
        problems: Receives ``(line, message)`` pairs for invalid dates.

    Returns:
        The valid verification dates and whether the entry is superseded.
    """
    verified: list[date] = []
    superseded = False
    for body_number, line in body:
        stamp = _VERIFIED.match(line)
        if stamp:
            parsed = _parse_date(stamp.group(1))
            if parsed is None:
                problems.append((body_number, f"invalid date '{stamp.group(1)}'"))
            else:
                verified.append(parsed)
        superseded = superseded or bool(_SUPERSEDED.match(line))
    return tuple(verified), superseded


def entries(text: str) -> tuple[list[Entry], list[tuple[int, str]]]:
    """Split Markdown into dated entries and report malformed dates.

    An entry runs from a dated heading to the next heading of any level, so
    verification and status lines belong to the nearest heading above them.

    Args:
        text: The Markdown document.

    Returns:
        The dated entries and ``(line, message)`` pairs for invalid dates.
    """
    lines = list(_content_lines(text))
    headings = _headings(lines)
    found: list[Entry] = []
    problems: list[tuple[int, str]] = []
    for position, (index, title) in enumerate(headings):
        number = lines[index][0]
        match = _DATE.search(title)
        if not match:
            continue
        dated = _parse_date(match.group(0))
        if dated is None:
            problems.append((number, f"invalid date '{match.group(0)}'"))
            continue
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        verified, superseded = _entry_body(lines[index + 1 : end], problems)
        found.append(
            Entry(
                line=number,
                title=title,
                dated=dated,
                verified=verified,
                superseded=superseded,
            )
        )
    return found, sorted(set(problems))


def links(text: str) -> list[tuple[int, str]]:
    """Return local link targets with their line numbers, outside code fences.

    Args:
        text: The Markdown document.

    Returns:
        ``(line, target)`` pairs with anchors and percent-encoding removed.
    """
    found: list[tuple[int, str]] = []
    for number, line in _content_lines(text):
        for raw in _LINK.findall(line):
            target = raw.strip("<>")
            if target.startswith(_EXTERNAL):
                continue
            local = unquote(target.partition("#")[0])
            if local:
                found.append((number, local))
    return found


def scan(
    text: str,
    *,
    source: str,
    today: date,
    max_age_days: int,
    link_problem: Callable[[str], str | None],
) -> list[str]:
    """Report stale, future-dated or malformed entries and broken links.

    Args:
        text: The Markdown document.
        source: Display path used in findings.
        today: The reference date for age calculations.
        max_age_days: The largest accepted age in days.
        link_problem: Returns a message for an unusable link target, or None.

    Returns:
        ``path:line: message`` findings in line order.
    """
    findings: list[tuple[int, str]] = []
    found, problems = entries(text)
    findings.extend(problems)
    for entry in found:
        age = (today - entry.effective).days
        if entry.dated > today:
            findings.append((entry.line, f"entry date {entry.dated} is in the future"))
        elif not entry.superseded and age > max_age_days:
            findings.append(
                (
                    entry.line,
                    (
                        f"entry '{entry.title}' was last verified {age} days ago "
                        f"(limit {max_age_days}); re-verify or mark it superseded"
                    ),
                )
            )
    for number, target in links(text):
        problem = link_problem(target)
        if problem:
            findings.append((number, f"link '{target}' {problem}"))
    return [f"{source}:{line}: {message}" for line, message in sorted(findings)]


def file_link_checker(document: Path, root: Path) -> Callable[[str], str | None]:
    """Build a link resolver for one document on disk.

    Args:
        document: The Markdown file containing the links.
        root: The directory that every link must stay inside.

    Returns:
        A function returning a problem message or None for each target.
    """
    base = root.resolve()

    def problem(target: str) -> str | None:
        if Path(target).is_absolute() or PureWindowsPath(target).drive:
            return "is absolute; use a relative path"
        resolved = (document.parent / target).resolve()
        if not resolved.is_relative_to(base):
            return "leaves the checked root"
        if not resolved.exists():
            return "points to a missing file"
        return None

    return problem


class MemoryInputError(FileNotFoundError):
    """An input violates the memory input contract."""

    def __init__(self, *, path: Path) -> None:
        """Describe the violated invariant.

        Args:
            path: Diagnostic path for the failing input.
        """
        super().__init__(f"no such file or directory: {path}")


def markdown_files(paths: list[Path]) -> list[Path]:
    """Expand files and directories into a sorted list of Markdown files.

    Args:
        paths: Files or directories to scan.

    Returns:
        Unique Markdown files in path order.

    Raises:
        FileNotFoundError: A requested path does not exist.
    """
    found: set[Path] = set()
    for path in paths:
        if path.is_dir():
            found.update(item for item in path.rglob("*.md") if item.is_file())
        elif path.is_file():
            found.add(path)
        else:
            raise MemoryInputError(path=path)
    return sorted(found)


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    UNEXPECTED_FINDINGS = "unexpected findings: {findings}"
    FRESH_ENTRY_REJECTED = "a fresh entry must pass"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(
        self, issue: SelfTestIssue, *, findings: list[str] | None = None
    ) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
            findings: Observed findings for the failing case.
        """
        super().__init__(issue.value.format(findings=findings))


def self_test() -> None:
    """Exercise entry parsing, ageing and link checks with in-memory text.

    Raises:
        AssertionError: A synthetic case produced an unexpected result.
    """
    today = _SELF_TEST_TODAY
    document = (
        "# Memory\n\n"
        "## 2026-06-01 Fresh entry\n\nSee [guide](guide.md).\n\n"
        "## 2025-01-10 Old but re-verified\n\n- Last verified: 2026-05-20\n\n"
        "## 2024-02-02 Retired approach\n\n- Status: superseded\n\n"
        "## 2025-02-01 Stale entry\n\n```md\n[ignored](nowhere.md)\n```\n"
        "[gone](missing.md) and [web](https://example.com/x)\n\n"
        "## 2026-02-30 Impossible date\n\n## 2027-01-01 Future entry\n"
    )

    def fake(target: str) -> str | None:
        return None if target == "guide.md" else "points to a missing file"

    findings = scan(
        document,
        source="m.md",
        today=today,
        max_age_days=_SELF_TEST_MAX_AGE_DAYS,
        link_problem=fake,
    )
    expected = [
        (
            "m.md:15: entry '2025-02-01 Stale entry' was last verified 514 days "
            "ago (limit 90); re-verify or mark it superseded"
        ),
        "m.md:20: link 'missing.md' points to a missing file",
        "m.md:22: invalid date '2026-02-30'",
        "m.md:24: entry date 2027-01-01 is in the future",
    ]
    if findings != expected:
        raise SelfTestError(SelfTestIssue.UNEXPECTED_FINDINGS, findings=findings)
    if scan(
        "## 2026-06-29 New\n",
        source="n",
        today=today,
        max_age_days=1,
        link_problem=fake,
    ):
        raise SelfTestError(SelfTestIssue.FRESH_ENTRY_REJECTED)


def _scan_paths(
    paths: list[Path], *, root: Path, today: date, max_age_days: int
) -> list[str]:
    """Scan every Markdown file under ``paths`` and return all findings.

    Args:
        paths: Files or directories to scan.
        root: The directory that every link must stay inside.
        today: The reference date for age calculations.
        max_age_days: The largest accepted age in days.

    Returns:
        Findings for all scanned files in path order.
    """
    findings: list[str] = []
    for path in markdown_files(paths):
        findings.extend(
            scan(
                path.read_text(encoding="utf-8"),
                source=path.as_posix(),
                today=today,
                max_age_days=max_age_days,
                link_problem=file_link_checker(path, root),
            )
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    """Scan memory and decision files for stale entries and broken links.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        0 when clean, 1 on findings, 2 on unreadable input.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "paths", nargs="*", type=Path, help="files or directories (default: memories)"
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--max-age-days", type=int, default=_DEFAULT_MAX_AGE_DAYS)
    parser.add_argument(
        "--today", type=date.fromisoformat, help="reference date, YYYY-MM-DD"
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("Memory freshness checker self-test passed.")
        return 0
    if args.max_age_days < 0:
        parser.error("--max-age-days must not be negative")
    today = args.today or datetime.now(tz=UTC).date()
    try:
        findings = _scan_paths(
            args.paths or [Path("memories")],
            root=args.root,
            today=today,
            max_age_days=args.max_age_days,
        )
    except (OSError, UnicodeError) as error:
        print(f"Cannot read memory files: {error}", file=sys.stderr)
        return _EXIT_USAGE
    for finding in findings:
        print(finding)
    if not findings:
        print("Memory entries are fresh and their local links resolve.")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
