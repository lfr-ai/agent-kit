"""Validate project memory files: dated entries, required fields, links and age.

Two shapes are recognized in each Markdown file:

- Dated entries: headings at ``--entry-level`` (default 2) whose title starts
  with an ISO date, such as ``## 2026-10-23 Lockfile needs the CI uv``. Once a
  file has one dated entry heading, every heading at that level must be dated.
  Each entry needs the ``--require`` fields (default ``Status`` and
  ``Evidence``), written as ``- Field: value`` lines in its body.
- Records: files whose YAML-style front matter declares ``status`` or
  ``date`` (decision records). Records need both fields.

For both shapes the status must be one of ``active``, ``proposed``,
``accepted``, ``rejected``, ``deprecated`` or ``superseded``; a superseded
entry or record must link its replacement in the status value or in a
``Superseded by`` field. Dates must be real and not in the future. An entry
whose newest date (heading or ``Last verified:``) is older than
``--max-age-days`` is stale unless its status is historical (superseded,
rejected or deprecated). Records are permanent and are not aged.

In every scanned file, local links must be relative, stay inside ``--root``
and point to an existing file or folder. Web links and anchors are not
fetched. Fenced code blocks and HTML comments are ignored, so template
guidance in comments is not validated.

With ``--freshness-only`` the checker runs the lenient freshness check for
repositories whose memory files carry no structured fields: required fields,
the status vocabulary, supersession links and the every-heading-dated rule
are skipped. Date validity, future dates, staleness (refreshed by a
``Last verified:``, ``Verified:`` or ``Reviewed:`` date), the exemption of
historical entries and all link checks still apply.

Findings are printed as ``path:line: message`` in path order. Exit status: 0
when clean, 1 on findings, 2 when an input cannot be read or arguments are
invalid.

Example:
    python check_memory_files.py memories docs/decisions --root . --max-age-days 120
    python check_memory_files.py memories --freshness-only --max-age-days 180
"""

import argparse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path, PureWindowsPath
import re
import sys
from urllib.parse import unquote

_HEADING = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$")
_DATE_PREFIX = re.compile(r"^(?P<text>\d{4}-\d{1,2}-\d{1,2})\b")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_FIELD = re.compile(
    r"^\s*(?:[-*]\s+)?\**(?P<key>[A-Za-z][A-Za-z -]{0,29}?)\**\s*:\**\s*(?P<value>.*)$"
)
_LINK = re.compile(r"!?\[[^\]]*\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
_INLINE_CODE = re.compile(r"`[^`]*`")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_FENCE = re.compile(r"^\s*(```|~~~)")
_FRONT_MATTER_FENCE = "---"
_COMMENT_OPEN = "<!--"
# HTML ends a comment at "-->" and also at the "--!>" error-recovery form.
_COMMENT = re.compile(r"<!--.*?--!?>", re.DOTALL)
_COMMENT_CLOSE = re.compile(r"--!?>")
_MARKDOWN_LINK = "]("
_EXIT_FINDINGS = 1
_EXIT_USAGE = 2
_DEFAULT_MAX_AGE_DAYS = 180
_DEFAULT_ENTRY_LEVEL = 2
_MAX_HEADING_LEVEL = 6
_DEFAULT_REQUIRED = ("Status", "Evidence")
_RECORD_REQUIRED = ("status", "date")
_ALLOWED_STATUS = frozenset(
    {"active", "proposed", "accepted", "rejected", "deprecated", "superseded"}
)
_HISTORICAL_STATUS = frozenset({"superseded", "rejected", "deprecated"})
_VERIFIED_KEYS = ("last verified", "last-verified", "verified", "reviewed")
_SUPERSEDED_KEYS = ("superseded by", "superseded-by")
_SELF_TEST_TODAY = date(2026, 10, 23)
_SELF_TEST_MAX_AGE_DAYS = 90
_SELF_TEST_DOCUMENT = """# Lessons
<!--
- Status: ignored inside a comment
-->
## 2026-10-01 Fresh and complete
- Status: active
- Evidence: `uv run pytest` passed
## 2025-01-01 Old entry
- Status: active
- Evidence: a test
## Undated entry
## 2026-02-30 Impossible date
- Status: maybe
## 2026-03-01 Replaced
- Status: superseded
- Evidence: a test
See [missing](does-not-exist.md) and [web](https://example.com).
```
[ignored](nowhere.md)
```
"""


@dataclass(frozen=True, kw_only=True, slots=True)
class Policy:
    """Settings shared by every file check.

    Attributes:
        root: Directory that local links must stay inside.
        today: Reference date for age and future-date checks.
        max_age_days: Age after which an active entry is stale.
        entry_level: Heading level of dated entries.
        required: Field names every dated entry must contain.
        freshness_only: Check only dates, staleness and links.
    """

    root: Path
    today: date
    max_age_days: int = _DEFAULT_MAX_AGE_DAYS
    entry_level: int = _DEFAULT_ENTRY_LEVEL
    required: tuple[str, ...] = _DEFAULT_REQUIRED
    freshness_only: bool = False


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One problem in one file.

    Attributes:
        path: File as given on the command line or found below a folder.
        line: 1-based line number.
        message: Human-readable description.
    """

    path: str
    line: int
    message: str

    def render(self) -> str:
        """Return the finding as ``path:line: message``."""
        return f"{self.path}:{self.line}: {self.message}"


@dataclass(frozen=True, kw_only=True, slots=True)
class Block:
    """A dated entry or a front-matter record and its fields.

    Attributes:
        kind: ``entry`` or ``record``.
        line: 1-based line of the heading or front matter start.
        label: Heading title or file name used in messages.
        date_text: The date as written, or an empty string when absent.
        fields: Lower-case field name mapped to its line and value.
        aged: Whether the block can become stale.
    """

    kind: str
    line: int
    label: str
    date_text: str
    fields: Mapping[str, tuple[int, str]]
    aged: bool


def _parse_date(text: str) -> date | None:
    """Parse an ISO calendar date, returning None when it is not a real date."""
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def content_lines(text: str) -> list[tuple[int, str]]:
    """Return numbered lines outside fenced code blocks and HTML comments.

    Args:
        text: Markdown file content.

    Returns:
        ``(line number, line)`` pairs; single-line comments are removed in place.
    """
    kept: list[tuple[int, str]] = []
    fence: str | None = None
    in_comment = False
    for number, raw in enumerate(text.splitlines(), start=1):
        match = _FENCE.match(raw)
        if fence is None and match and not in_comment:
            fence = match.group(1)
        elif fence is not None:
            fence = None if raw.strip().startswith(fence) else fence
        elif in_comment:
            in_comment = _COMMENT_CLOSE.search(raw) is None
        else:
            line = _COMMENT.sub("", raw)
            in_comment = _COMMENT_OPEN in line
            kept.append((number, line.split(_COMMENT_OPEN, 1)[0]))
    return kept


def _fields(lines: Iterable[tuple[int, str]]) -> dict[str, tuple[int, str]]:
    """Collect ``Field: value`` lines; the first occurrence of a field wins."""
    found: dict[str, tuple[int, str]] = {}
    for number, line in lines:
        match = _FIELD.match(line)
        if match:
            found.setdefault(match["key"].strip().lower(), (number, match["value"]))
    return found


def _front_matter(lines: list[tuple[int, str]]) -> Block | None:
    """Return the record declared by leading front matter, if any."""
    if not lines or lines[0][1].strip() != _FRONT_MATTER_FENCE:
        return None
    body: list[tuple[int, str]] = []
    for number, line in lines[1:]:
        if line.strip() == _FRONT_MATTER_FENCE:
            fields = _fields(body)
            if not any(key in fields for key in _RECORD_REQUIRED):
                return None
            date_text = fields.get("date", (0, ""))[1].strip().strip("\"'")
            return Block(
                kind="record",
                line=lines[0][0],
                label="front matter",
                date_text=date_text,
                fields=fields,
                aged=False,
            )
        body.append((number, line))
    return None


def _headings(lines: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
    """Return ``(index, level, title)`` for every heading line."""
    found: list[tuple[int, int, str]] = []
    for index, (_, line) in enumerate(lines):
        match = _HEADING.match(line)
        if match:
            found.append((index, len(match["marks"]), match["title"]))
    return found


def _entries(
    lines: list[tuple[int, str]], *, level: int
) -> tuple[list[Block], list[tuple[int, str]]]:
    """Split dated entries at ``level`` and report undated sibling headings."""
    headings = _headings(lines)
    entry_headings = [item for item in headings if item[1] == level]
    if not any(_DATE_PREFIX.match(title) for _, _, title in entry_headings):
        return [], []
    blocks: list[Block] = []
    problems: list[tuple[int, str]] = []
    for index, _, title in entry_headings:
        end = next(
            (other for other, depth, _ in headings if other > index and depth <= level),
            len(lines),
        )
        match = _DATE_PREFIX.match(title)
        if match is None:
            problems.append((lines[index][0], f"entry heading '{title}' has no date"))
            continue
        blocks.append(
            Block(
                kind="entry",
                line=lines[index][0],
                label=title,
                date_text=match["text"],
                fields=_fields(lines[index + 1 : end]),
                aged=True,
            )
        )
    return blocks, problems


def _status_problems(block: Block) -> list[tuple[int, str]]:
    """Check the status value and the replacement link of superseded blocks."""
    if "status" not in block.fields:
        return []
    line, value = block.fields["status"]
    words = value.strip().strip("`*").split()
    status = words[0].lower().strip(".,;") if words else ""
    if status not in _ALLOWED_STATUS:
        allowed = ", ".join(sorted(_ALLOWED_STATUS))
        return [(line, f"{block.kind} status '{status}' is not one of: {allowed}")]
    links = [value] + [
        block.fields[key][1] for key in _SUPERSEDED_KEYS if key in block.fields
    ]
    if status == "superseded" and not any(_MARKDOWN_LINK in item for item in links):
        return [(line, f"superseded {block.kind} does not link its replacement")]
    return []


def _newest_date(block: Block, dated: date) -> date:
    """Return the newest of the block date and its verification dates."""
    verified = [
        parsed
        for key in _VERIFIED_KEYS
        if key in block.fields
        for text in _ISO_DATE.findall(block.fields[key][1])
        if (parsed := _parse_date(text)) is not None
    ]
    return max((dated, *verified))


def _date_problems(block: Block, *, policy: Policy) -> list[tuple[int, str]]:
    """Check date validity, future dates and age of one block."""
    if not block.date_text:
        return []
    dated = _parse_date(block.date_text)
    if dated is None:
        return [
            (block.line, f"{block.kind} date '{block.date_text}' is not a real date")
        ]
    if dated > policy.today:
        return [(block.line, f"{block.kind} date {dated} is in the future")]
    status = block.fields.get("status", (0, ""))[1].strip().strip("`*").lower()
    if not block.aged or status.startswith(tuple(_HISTORICAL_STATUS)):
        return []
    age = (policy.today - _newest_date(block, dated)).days
    if age <= policy.max_age_days:
        return []
    message = (
        f"entry '{block.label}' was last verified {age} days ago "
        f"(limit {policy.max_age_days}); re-verify it or mark it superseded"
    )
    return [(block.line, message)]


def _block_problems(block: Block, *, policy: Policy) -> list[tuple[int, str]]:
    """Check required fields, status and dates of one entry or record."""
    required = policy.required if block.kind == "entry" else _RECORD_REQUIRED
    missing = [
        (block.line, f"{block.kind} '{block.label}' is missing field '{name}'")
        for name in required
        if name.lower() not in block.fields
    ]
    if policy.freshness_only:
        return _date_problems(block, policy=policy)
    return [*missing, *_status_problems(block), *_date_problems(block, policy=policy)]


def _link_problem(target: str, *, source: Path, root: Path) -> str | None:
    """Describe why a local link target is unusable, if it is."""
    local = unquote(target.split("#", 1)[0])
    if not local:
        return None
    if local.startswith(("/", "\\")) or PureWindowsPath(local).drive:
        return f"link '{target}' is absolute; use a relative path"
    if _SCHEME.match(local):
        return None
    resolved = (source.parent / local).resolve()
    if not resolved.is_relative_to(root.resolve()):
        return f"link '{target}' leaves the checked root"
    if not resolved.exists():
        return f"link '{target}' points to a missing file"
    return None


def _link_problems(
    lines: list[tuple[int, str]], *, source: Path, root: Path
) -> list[tuple[int, str]]:
    """Check every local Markdown link outside inline code."""
    problems: list[tuple[int, str]] = []
    for number, line in lines:
        for match in _LINK.finditer(_INLINE_CODE.sub("", line)):
            problem = _link_problem(match["target"], source=source, root=root)
            if problem:
                problems.append((number, problem))
    return problems


def check_text(text: str, *, source: Path, shown: str, policy: Policy) -> list[Finding]:
    """Check one Markdown document.

    Args:
        text: File content.
        source: File location used to resolve relative links.
        shown: Path printed in findings.
        policy: Shared settings.

    Returns:
        Findings sorted by line and message.
    """
    lines = content_lines(text)
    record = _front_matter(lines)
    blocks, undated = _entries(lines, level=policy.entry_level)
    problems = [] if policy.freshness_only else undated
    if record is not None:
        blocks.insert(0, record)
    for block in blocks:
        problems.extend(_block_problems(block, policy=policy))
    problems.extend(_link_problems(lines, source=source, root=policy.root))
    return [
        Finding(path=shown, line=line, message=message)
        for line, message in sorted(set(problems))
    ]


def collect(paths: Iterable[Path]) -> list[Path]:
    """Expand folders to the Markdown files below them.

    Args:
        paths: Files or folders.

    Returns:
        Markdown files in a stable order.

    Raises:
        FileNotFoundError: A path does not exist.
    """
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(path.rglob("*.md")))
        elif path.is_file():
            found.append(path)
        else:
            message = f"{path.as_posix()}: no such file or folder"
            raise FileNotFoundError(message)
    return found


def _render_self_test(policy: Policy) -> str:
    """Return the rendered findings for the built-in sample document."""
    return "\n".join(
        finding.render()
        for finding in check_text(
            _SELF_TEST_DOCUMENT,
            source=policy.root / "lessons.md",
            shown="lessons.md",
            policy=policy,
        )
    )


def _unmet(
    rendered: str, *, expected: Iterable[str], absent: Iterable[str]
) -> list[str]:
    """List expected findings that are missing and forbidden text that appears."""
    missing = [f"expected {needle!r}" for needle in expected if needle not in rendered]
    present = [
        f"unexpected finding containing {text!r}" for text in absent if text in rendered
    ]
    return [*missing, *present]


def self_test() -> list[str]:
    """Check the rules on in-memory documents and return unmet expectations.

    The sample is checked twice: with the full rules and with
    ``--freshness-only``, which must report only date, age and link findings.

    Returns:
        Descriptions of failed expectations; empty when the checker works.
    """
    policy = Policy(
        root=Path.cwd(), today=_SELF_TEST_TODAY, max_age_days=_SELF_TEST_MAX_AGE_DAYS
    )
    lenient = (
        "lessons.md:8: entry '2025-01-01 Old entry' was last verified",
        "lessons.md:12: entry date '2026-02-30' is not a real date",
        "lessons.md:17: link 'does-not-exist.md' points to a missing file",
    )
    strict = (
        "lessons.md:11: entry heading 'Undated entry' has no date",
        "lessons.md:12: entry '2026-02-30 Impossible date' is missing field 'Evidence'",
        "lessons.md:13: entry status 'maybe'",
        "lessons.md:15: superseded entry does not link",
    )
    clean = ("Fresh and complete", "ignored", "example.com", "nowhere.md")
    full = _unmet(_render_self_test(policy), expected=(*lenient, *strict), absent=clean)
    freshness = _unmet(
        _render_self_test(replace(policy, freshness_only=True)),
        expected=lenient,
        absent=(*clean, "has no date", "missing field", "status", "does not link"),
    )
    return [*full, *(f"--freshness-only: {item}" for item in freshness)]


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "paths", nargs="*", type=Path, help="Markdown files or folders to check"
    )
    parser.add_argument("--root", type=Path, default=Path(), help="link boundary")
    parser.add_argument(
        "--max-age-days", type=int, default=_DEFAULT_MAX_AGE_DAYS, help="stale limit"
    )
    parser.add_argument(
        "--entry-level",
        type=int,
        default=_DEFAULT_ENTRY_LEVEL,
        choices=range(1, _MAX_HEADING_LEVEL + 1),
        help="heading level of dated entries",
    )
    parser.add_argument(
        "--require",
        action="append",
        metavar="FIELD",
        help="required entry field; repeatable; default Status and Evidence",
    )
    parser.add_argument("--today", help="reference date as YYYY-MM-DD")
    parser.add_argument(
        "--freshness-only",
        action="store_true",
        help="check only dates, staleness and links; skip field and status rules",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in checks and exit"
    )
    return parser


def _run_self_test() -> int:
    """Run the self-test, print its outcome and return the exit status."""
    failures = self_test()
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return _EXIT_FINDINGS
    print("check_memory_files self-test passed.")
    return 0


def _policy(args: argparse.Namespace) -> Policy | str:
    """Build the policy from arguments, or return a usage error message."""
    today = datetime.now(tz=UTC).date()
    if args.today:
        parsed = _parse_date(args.today)
        if parsed is None:
            return f"--today '{args.today}' is not a YYYY-MM-DD date"
        today = parsed
    if args.max_age_days < 0:
        return "--max-age-days must not be negative"
    if not args.root.is_dir():
        return f"{args.root.as_posix()}: root is not a folder"
    return Policy(
        root=args.root,
        today=today,
        max_age_days=args.max_age_days,
        entry_level=args.entry_level,
        required=tuple(args.require or _DEFAULT_REQUIRED),
        freshness_only=args.freshness_only,
    )


def main(argv: list[str] | None = None) -> int:
    """Check memory files and print findings.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when None.

    Returns:
        0 when clean, 1 when findings exist, 2 on unreadable input or bad arguments.
    """
    args = _parser().parse_args(argv)
    if args.self_test:
        return _run_self_test()
    policy = _policy(args)
    if isinstance(policy, str):
        print(policy, file=sys.stderr)
        return _EXIT_USAGE
    try:
        files = collect(args.paths or [Path("memories")])
        texts = [(path, path.read_text(encoding="utf-8")) for path in files]
    except (OSError, UnicodeDecodeError) as error:
        print(error, file=sys.stderr)
        return _EXIT_USAGE
    findings = [
        finding
        for path, text in texts
        for finding in check_text(
            text, source=path, shown=path.as_posix(), policy=policy
        )
    ]
    for finding in findings:
        print(finding.render())
    if not findings:
        print(f"Memory files are valid: {len(files)} file(s) checked.")
    return _EXIT_FINDINGS if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
