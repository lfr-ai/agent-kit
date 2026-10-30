# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Report the character size of agent context files that load on every request.

Always-on files found below ``--root``:

- entry files: ``AGENTS.md``, ``CLAUDE.md``, ``.claude/CLAUDE.md``,
  ``CLAUDE.local.md`` and ``.github/copilot-instructions.md``;
- files imported from a ``CLAUDE.md`` with ``@path`` (outside inline code and
  fenced blocks), followed up to four hops, counted once;
- ``*.instructions.md`` files under each ``--instructions-dir`` (default
  ``.github/instructions``) whose front matter ``applyTo`` includes ``**`` or
  ``**/*``;
- Markdown rules under ``.claude/rules`` without a ``paths`` front matter key;
- every ``--extra`` file.

Each file is counted in characters (Unicode code points of its UTF-8 text),
not tokens, because tokenization differs by model and host. A file over
``--max-file-chars`` or a total over ``--max-total-chars`` is a finding. Hosts
load different subsets of these files; the total is an upper bound across
hosts, not a per-host measurement.

Output is a table sorted by path, then findings as ``path:1: message``.
Exit status: 0 within limits, 1 on findings, 2 when the root or an extra file
cannot be read or a limit is not positive.

Example:
    python check_context_budget.py --root . --max-file-chars 8000 --max-total-chars 16000
"""

import argparse
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys

_ENTRY_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    ".claude/CLAUDE.md",
    "CLAUDE.local.md",
    ".github/copilot-instructions.md",
)
_CLAUDE_ENTRIES = frozenset({"CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"})
_DEFAULT_INSTRUCTIONS_DIR = ".github/instructions"
_CLAUDE_RULES_DIR = ".claude/rules"
_ALWAYS_ON_GLOBS = frozenset({"**", "**/*"})
_FRONT_MATTER_FENCE = "---"
_KEY_VALUE = re.compile(r"^(?P<key>[A-Za-z][\w-]*)\s*:\s*(?P<value>.*)$")
_IMPORT = re.compile(r"(?<![\w`@])@(?P<path>[\w~./-]+)")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_FENCE = re.compile(r"^\s*(```|~~~)")
_MAX_IMPORT_HOPS = 4
_DEFAULT_MAX_FILE_CHARS = 8000
_DEFAULT_MAX_TOTAL_CHARS = 16000
_EXIT_FINDINGS = 1
_EXIT_USAGE = 2
_COLUMN_WIDTH = 8
_KIND_WIDTH = 12
_JSON_INDENT = 2
_SELF_TEST_LARGE_CHARS = 90
_SELF_TEST_SMALL_CHARS = 20
_SELF_TEST_FILE_LIMIT = 50
_SELF_TEST_TOTAL_LIMIT = 100


@dataclass(frozen=True, kw_only=True, slots=True)
class ContextFile:
    """One always-on file and its size.

    Attributes:
        path: Path relative to the root, with forward slashes.
        kind: ``entry``, ``import``, ``instruction``, ``rule`` or ``extra``.
        chars: Number of characters in the file.
    """

    path: str
    kind: str
    chars: int


@dataclass(frozen=True, kw_only=True, slots=True)
class Limits:
    """Character limits to compare against.

    Attributes:
        max_file_chars: Largest allowed single file.
        max_total_chars: Largest allowed sum over all files.
    """

    max_file_chars: int = _DEFAULT_MAX_FILE_CHARS
    max_total_chars: int = _DEFAULT_MAX_TOTAL_CHARS


def front_matter(text: str) -> dict[str, str]:
    """Return top-level ``key: value`` pairs of leading front matter.

    Args:
        text: Markdown content.

    Returns:
        Keys mapped to their raw values; empty when there is no front matter.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONT_MATTER_FENCE:
        return {}
    found: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == _FRONT_MATTER_FENCE:
            return found
        match = _KEY_VALUE.match(line)
        if match:
            found[match["key"]] = match["value"].strip()
    return {}


def is_always_on_instruction(text: str) -> bool:
    """Return whether an instructions file applies to every file.

    Args:
        text: Content of a ``*.instructions.md`` file.

    Returns:
        True when one ``applyTo`` pattern is ``**`` or ``**/*``.
    """
    scope = front_matter(text).get("applyTo", "").strip("\"'")
    return any(item.strip() in _ALWAYS_ON_GLOBS for item in scope.split(","))


def is_unscoped_rule(text: str) -> bool:
    """Return whether a Claude rule has no ``paths`` key and so always loads.

    Args:
        text: Content of a Markdown file under ``.claude/rules``.

    Returns:
        True when the front matter has no ``paths`` key.
    """
    return "paths" not in front_matter(text)


def imports(text: str) -> list[str]:
    """Return ``@path`` import targets outside code spans and fenced blocks.

    Args:
        text: Content of a ``CLAUDE.md`` file.

    Returns:
        Import targets in order of appearance, without the ``@``.
    """
    found: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        match = _FENCE.match(line)
        if fence is None and match:
            fence = match.group(1)
        elif fence is not None:
            fence = None if line.strip().startswith(fence) else fence
        else:
            found.extend(
                item["path"] for item in _IMPORT.finditer(_INLINE_CODE.sub("", line))
            )
    return found


def _read(path: Path) -> str:
    """Read a UTF-8 text file."""
    return path.read_text(encoding="utf-8")


def _relative(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` with forward slashes."""
    return path.resolve().relative_to(root.resolve()).as_posix()


def _imported_files(entry: Path, *, root: Path) -> list[Path]:
    """Follow ``@`` imports from one Claude entry file up to the hop limit."""
    found: list[Path] = []
    pending = [(entry, 0)]
    seen = {entry.resolve()}
    while pending:
        source, hops = pending.pop(0)
        if hops >= _MAX_IMPORT_HOPS:
            continue
        for target in imports(_read(source)):
            resolved = (source.parent / target).resolve()
            inside = resolved.is_relative_to(root.resolve())
            if inside and resolved.is_file() and resolved not in seen:
                seen.add(resolved)
                found.append(resolved)
                pending.append((resolved, hops + 1))
    return found


def _scoped_files(
    root: Path, *, instruction_dirs: Sequence[str]
) -> list[tuple[Path, str]]:
    """Return always-on instructions and unscoped Claude rules."""
    instructions = [
        (path, "instruction")
        for directory in instruction_dirs
        for path in sorted((root / directory).rglob("*.instructions.md"))
        if is_always_on_instruction(_read(path))
    ]
    rules = [
        (path, "rule")
        for path in sorted((root / _CLAUDE_RULES_DIR).rglob("*.md"))
        if is_unscoped_rule(_read(path))
    ]
    return [*instructions, *rules]


def discover(
    root: Path, *, instruction_dirs: Sequence[str], extras: Iterable[Path]
) -> list[ContextFile]:
    """Find always-on context files below ``root`` and measure them.

    Args:
        root: Repository root.
        instruction_dirs: Folders searched for ``*.instructions.md``.
        extras: Additional files that a host loads by default.

    Returns:
        Measured files sorted by path, each counted once.

    Raises:
        OSError: A discovered or extra file cannot be read.
        UnicodeDecodeError: A file is not UTF-8 text.
    """
    candidates: list[tuple[Path, str]] = []
    for name in _ENTRY_FILES:
        path = root / name
        if path.is_file():
            candidates.append((path, "entry"))
            if name in _CLAUDE_ENTRIES:
                candidates.extend(
                    (item, "import") for item in _imported_files(path, root=root)
                )
    candidates.extend(_scoped_files(root, instruction_dirs=instruction_dirs))
    candidates.extend((path, "extra") for path in extras)
    measured: dict[str, ContextFile] = {}
    for path, kind in candidates:
        key = path.resolve().as_posix()
        if key not in measured:
            shown = (
                _relative(path, root)
                if path.resolve().is_relative_to(root.resolve())
                else path.as_posix()
            )
            measured[key] = ContextFile(path=shown, kind=kind, chars=len(_read(path)))
    return sorted(measured.values(), key=lambda item: item.path)


def evaluate(files: Sequence[ContextFile], *, limits: Limits) -> list[str]:
    """Compare measured files with the limits.

    Args:
        files: Measured always-on files.
        limits: Per-file and total character limits.

    Returns:
        Findings rendered as ``path:1: message``.
    """
    findings = [
        f"{item.path}:1: {item.chars} characters exceeds the per-file limit of {limits.max_file_chars}"
        for item in files
        if item.chars > limits.max_file_chars
    ]
    total = sum(item.chars for item in files)
    if total > limits.max_total_chars:
        findings.append(
            f"(total):1: {total} always-on characters exceeds the total limit of {limits.max_total_chars}"
        )
    return findings


def render(files: Sequence[ContextFile]) -> list[str]:
    """Format measured files as an aligned text table with a total row.

    Args:
        files: Measured always-on files.

    Returns:
        Table lines.
    """
    lines = [f"{'chars':>{_COLUMN_WIDTH}}  {'kind':<{_KIND_WIDTH}}path"]
    lines.extend(
        f"{item.chars:>{_COLUMN_WIDTH}}  {item.kind:<{_KIND_WIDTH}}{item.path}"
        for item in files
    )
    total = sum(item.chars for item in files)
    lines.append(
        f"{total:>{_COLUMN_WIDTH}}  {'total':<{_KIND_WIDTH}}{len(files)} file(s)"
    )
    return lines


def self_test() -> list[str]:
    """Check the parsing and limit rules on in-memory inputs.

    Returns:
        Descriptions of failed expectations; empty when the checker works.
    """
    failures: list[str] = []
    cases = {
        "applyTo ** is always on": is_always_on_instruction(
            '---\napplyTo: "**"\n---\n'
        ),
        "applyTo list with **/* is always on": is_always_on_instruction(
            "---\napplyTo: 'src/**,**/*'\n---\n"
        ),
        "narrow applyTo is scoped": not is_always_on_instruction(
            '---\napplyTo: "**/*.py"\n---\n'
        ),
        "missing applyTo is not always on": not is_always_on_instruction("# Notes\n"),
        "rule without paths is unscoped": is_unscoped_rule("# Rule\n"),
        "rule with paths is scoped": not is_unscoped_rule(
            '---\npaths:\n  - "src/**"\n---\n'
        ),
        "imports skip code": imports(
            "@AGENTS.md and `@skip.md`\n```\n@fenced.md\n```\nmail a@b.c\n"
        )
        == ["AGENTS.md"],
    }
    failures.extend(label for label, passed in cases.items() if not passed)
    files = [
        ContextFile(path="AGENTS.md", kind="entry", chars=_SELF_TEST_LARGE_CHARS),
        ContextFile(path="CLAUDE.md", kind="entry", chars=_SELF_TEST_SMALL_CHARS),
    ]
    limits = Limits(
        max_file_chars=_SELF_TEST_FILE_LIMIT, max_total_chars=_SELF_TEST_TOTAL_LIMIT
    )
    total = _SELF_TEST_LARGE_CHARS + _SELF_TEST_SMALL_CHARS
    expected = [
        (
            f"AGENTS.md:1: {_SELF_TEST_LARGE_CHARS} characters exceeds the per-file "
            f"limit of {_SELF_TEST_FILE_LIMIT}"
        ),
        (
            f"(total):1: {total} always-on characters exceeds the total limit of "
            f"{_SELF_TEST_TOTAL_LIMIT}"
        ),
    ]
    findings = evaluate(files, limits=limits)
    if findings != expected:
        failures.append(f"limit findings were {findings}")
    return failures


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=Path(), help="repository root")
    parser.add_argument("--max-file-chars", type=int, default=_DEFAULT_MAX_FILE_CHARS)
    parser.add_argument("--max-total-chars", type=int, default=_DEFAULT_MAX_TOTAL_CHARS)
    parser.add_argument(
        "--instructions-dir",
        action="append",
        metavar="DIR",
        help="folder searched for *.instructions.md; repeatable",
    )
    parser.add_argument(
        "--extra",
        action="append",
        type=Path,
        default=[],
        metavar="FILE",
        help="additional always-loaded file; repeatable",
    )
    parser.add_argument(
        "--json", action="store_true", help="print JSON instead of a table"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in checks and exit"
    )
    return parser


def _run_self_test() -> int:
    """Run the self-test, print its outcome and return the exit status."""
    failures = self_test()
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    if failures:
        return _EXIT_FINDINGS
    sys.stdout.write("check_context_budget self-test passed.\n")
    return 0


def _usage_error(args: argparse.Namespace) -> str | None:
    """Describe invalid arguments, if any."""
    if args.max_file_chars <= 0 or args.max_total_chars <= 0:
        return "character limits must be positive"
    if not args.root.is_dir():
        return f"{args.root.as_posix()}: root is not a folder"
    missing = [path.as_posix() for path in args.extra if not path.is_file()]
    if missing:
        return f"extra file not found: {', '.join(missing)}"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """Measure always-on context files and report limit findings.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when None.

    Returns:
        0 within limits, 1 on findings, 2 on unreadable input or bad arguments.
    """
    args = _parser().parse_args(argv)
    if args.self_test:
        return _run_self_test()
    error = _usage_error(args)
    if error:
        sys.stderr.write(f"{error}\n")
        return _EXIT_USAGE
    try:
        files = discover(
            args.root,
            instruction_dirs=args.instructions_dir or [_DEFAULT_INSTRUCTIONS_DIR],
            extras=args.extra,
        )
    except (OSError, UnicodeDecodeError) as problem:
        sys.stderr.write(f"{problem}\n")
        return _EXIT_USAGE
    limits = Limits(
        max_file_chars=args.max_file_chars, max_total_chars=args.max_total_chars
    )
    findings = evaluate(files, limits=limits)
    if args.json:
        payload = {
            "files": [
                {"path": item.path, "kind": item.kind, "chars": item.chars}
                for item in files
            ],
            "total": sum(item.chars for item in files),
            "limits": {"file": limits.max_file_chars, "total": limits.max_total_chars},
            "findings": findings,
        }
        sys.stdout.write(
            f"{json.dumps(payload, indent=_JSON_INDENT, sort_keys=True)}\n"
        )
    else:
        sys.stdout.write(f"{'\n'.join([*render(files), *findings])}\n")
    return _EXIT_FINDINGS if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
