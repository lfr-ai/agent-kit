"""Check that a worker handoff carries changed paths, evidence and limitations.

A handoff is a Markdown file returned by a delegated worker. Sections are
found by heading text (any level), for example ``## Changed paths``,
``## Evidence`` and ``## Limitations``. When no heading names a required
section, top-level numbered items such as ``1. Changed and created paths.``
are used as section markers instead, so short list-style handoffs also work.

Rules:

- Changed paths: the section exists and lists at least one path-like token
  (``src/app.py``, ``README.md``) or says ``none`` for read-only work.
- Evidence: the section exists, has at least one command in inline code, and
  every line or table row with a command also records a result on the same
  line: a word such as ``pass``, ``fail``, ``ok``, ``clean``, ``skipped``,
  ``not run``, an ``exit N`` phrase, ``N passed``, or an integer exit-code
  table cell.
- Limitations: the section exists and is not empty (``none`` is allowed).
- No unfilled template placeholders such as ``<path>`` remain outside inline
  code and HTML comments.

Fenced code blocks and HTML comments are ignored. Findings are printed as
``path:line: message``. Exit status: 0 when every handoff passes, 1 on
findings, 2 when a file cannot be read.

Example:
    python check_handoff.py handoffs/task-1.md handoffs/task-2.md
"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import re
import sys

_HEADING = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
_NUMBERED = re.compile(r"^(?P<number>\d+)[.)]\s+(?P<title>.+)$")
_FENCE = re.compile(r"^\s*(```|~~~)")
# HTML ends a comment at "-->" and also at the "--!>" error-recovery form.
_COMMENT = re.compile(r"<!--.*?--!?>", re.DOTALL)
_COMMENT_CLOSE = re.compile(r"--!?>")
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_PATH_TOKEN = re.compile(r"[\w.-]+/[\w./-]*|\b[\w-]+\.[A-Za-z][\w]{0,9}\b")
_NONE = re.compile(r"\bnone\b", re.IGNORECASE)
_RESULT = re.compile(
    r"\b(?:pass(?:ed|es)?|fail(?:ed|s|ure)?|ok|errors?|clean|succeeded|success"
    r"|skipped|not run|unavailable|valid|invalid|exit(?:ed)?(?: code)?:? ?-?\d+"
    r"|\d+ (?:passed|failed|errors?|findings?|warnings?)|no (?:findings|issues|errors))\b",
    re.IGNORECASE,
)
_EXIT_CODE_CELL = re.compile(r"^-?\d+$")
_PLACEHOLDER = re.compile(r"<(?P<name>[A-Za-z][^<>\n]{0,79})>")
_HTML_TAGS = frozenset(
    {"br", "b", "i", "em", "strong", "code", "kbd", "sub", "sup", "details", "summary"}
)
_SECTIONS = {
    "changed paths": re.compile(
        r"\b(?:changed|created|modified)\b.*\b(?:paths?|files?)\b", re.IGNORECASE
    ),
    "evidence": re.compile(r"\b(?:evidence|verification|commands?)\b", re.IGNORECASE),
    "limitations": re.compile(
        r"\b(?:limitations?|not verified|unverified|open items|known issues)\b",
        re.IGNORECASE,
    ),
}
_EXIT_FINDINGS = 1
_EXIT_USAGE = 2
_SELF_TEST_GOOD = """# Handoff
## Changed paths
- `src/orders/service.py`: modified
## Evidence
- `uv run pytest tests/unit/orders -q`: 12 passed
| Command | Exit | Result |
| --- | --- | --- |
| `uv run ruff check src` | 0 | |
## Limitations
- Not verified on Windows.
"""
_SELF_TEST_BAD = """# Handoff
## Changed paths
- <path>: modified
## Verification
- `uv run pytest`
"""
_SELF_TEST_LIST = """1. Changed and created paths: `docs/guide.md`.
2. Commands: `task verify -- docs`: passed.
3. Limitations: none.
"""


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One problem in one handoff.

    Attributes:
        path: Handoff file as given on the command line.
        line: 1-based line number; 1 for a missing section.
        message: Human-readable description.
    """

    path: str
    line: int
    message: str

    def render(self) -> str:
        """Return the finding as ``path:line: message``."""
        return f"{self.path}:{self.line}: {self.message}"


@dataclass(frozen=True, kw_only=True, slots=True)
class Section:
    """A required section located in the handoff.

    Attributes:
        line: 1-based line of the heading or numbered item.
        body: Numbered content lines, including text after a list marker label.
    """

    line: int
    body: tuple[tuple[int, str], ...]


def content_lines(text: str) -> list[tuple[int, str]]:
    """Return numbered lines outside fenced code blocks and HTML comments.

    Args:
        text: Markdown content.

    Returns:
        ``(line number, line)`` pairs with single-line comments removed.
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
            in_comment = "<!--" in line
            kept.append((number, line.split("<!--", 1)[0]))
    return kept


def _markers(lines: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
    """Return ``(index, depth, title)`` section markers.

    Headings are used when any heading names a required section; otherwise
    top-level numbered items are used, all at the same depth.
    """
    headings: list[tuple[int, int, str]] = []
    for index, (_, line) in enumerate(lines):
        match = _HEADING.match(line)
        if match:
            headings.append((index, len(match["marks"]), match["title"]))
    titles = [title for _, _, title in headings]
    if any(pattern.search(title) for pattern in _SECTIONS.values() for title in titles):
        return headings
    return [
        (index, 1, match["title"])
        for index, (_, line) in enumerate(lines)
        if (match := _NUMBERED.match(line))
    ]


def find_sections(lines: list[tuple[int, str]]) -> dict[str, Section]:
    """Locate each required section by its first matching marker.

    Args:
        lines: Content lines from ``content_lines``.

    Returns:
        Section name mapped to its location and body.
    """
    markers = _markers(lines)
    found: dict[str, Section] = {}
    for position, (index, depth, title) in enumerate(markers):
        end = next(
            (other for other, level, _ in markers[position + 1 :] if level <= depth),
            len(lines),
        )
        inline = _HEADING.match(lines[index][1]) is None
        body = ((lines[index][0], title),) if inline else ()
        section = Section(line=lines[index][0], body=(*body, *lines[index + 1 : end]))
        for name, pattern in _SECTIONS.items():
            if name not in found and pattern.search(title):
                found[name] = section
    return found


def _text(section: Section) -> str:
    """Join a section body into one string."""
    return "\n".join(line for _, line in section.body).strip()


def _changed_problems(section: Section) -> list[tuple[int, str]]:
    """Require at least one path or an explicit ``none``."""
    text = _text(section)
    if not text:
        return [(section.line, "section 'changed paths' is empty")]
    if _PATH_TOKEN.search(text) or _NONE.search(text):
        return []
    return [(section.line, "section 'changed paths' lists no path")]


def _has_result(line: str) -> bool:
    """Return whether a command line also records its result."""
    remainder = _INLINE_CODE.sub(" ", line)
    if _RESULT.search(remainder):
        return True
    cells = [cell.strip() for cell in remainder.split("|")]
    return any(_EXIT_CODE_CELL.match(cell) for cell in cells)


def _evidence_problems(section: Section) -> list[tuple[int, str]]:
    """Require commands in inline code, each with a result on its line."""
    commands = [
        (number, line, match[0])
        for number, line in section.body
        if (match := _INLINE_CODE.search(line))
    ]
    if not commands:
        return [(section.line, "section 'evidence' records no command in inline code")]
    return [
        (number, f"command {command} has no recorded result")
        for number, line, command in commands
        if not _has_result(line)
    ]


def _is_placeholder(name: str) -> bool:
    """Return whether bracketed text is a template placeholder, not HTML or a URL."""
    if "://" in name or "@" in name:
        return False
    return name.split(maxsplit=1)[0].lower().rstrip("/") not in _HTML_TAGS


def _placeholder_problems(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Report template placeholders that were left unfilled."""
    return [
        (number, f"unfilled placeholder '{match[0]}'")
        for number, line in lines
        for match in _PLACEHOLDER.finditer(_INLINE_CODE.sub("", line))
        if _is_placeholder(match["name"])
    ]


def check_text(text: str, *, shown: str) -> list[Finding]:
    """Check one handoff document.

    Args:
        text: Markdown content.
        shown: Path printed in findings.

    Returns:
        Findings sorted by line and message.
    """
    lines = content_lines(text)
    sections = find_sections(lines)
    problems = [
        (1, f"missing required section '{name}'")
        for name in _SECTIONS
        if name not in sections
    ]
    if "changed paths" in sections:
        problems.extend(_changed_problems(sections["changed paths"]))
    if "evidence" in sections:
        problems.extend(_evidence_problems(sections["evidence"]))
    if "limitations" in sections and not _text(sections["limitations"]):
        problems.append(
            (sections["limitations"].line, "section 'limitations' is empty")
        )
    problems.extend(_placeholder_problems(lines))
    return [
        Finding(path=shown, line=line, message=message)
        for line, message in sorted(set(problems))
    ]


def self_test() -> list[str]:
    """Check the rules on in-memory handoffs and return unmet expectations.

    Returns:
        Descriptions of failed expectations; empty when the checker works.
    """
    failures: list[str] = []
    for label, document in (
        ("table and list", _SELF_TEST_GOOD),
        ("numbered", _SELF_TEST_LIST),
    ):
        found = check_text(document, shown="good.md")
        if found:
            failures.append(f"valid {label} handoff reported: {found}")
    rendered = "\n".join(
        item.render() for item in check_text(_SELF_TEST_BAD, shown="bad.md")
    )
    expected = (
        "bad.md:1: missing required section 'limitations'",
        "bad.md:3: unfilled placeholder '<path>'",
        "bad.md:5: command `uv run pytest` has no recorded result",
    )
    failures.extend(
        f"expected {needle!r}" for needle in expected if needle not in rendered
    )
    return failures


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="*", type=Path, help="handoff Markdown files")
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
    print("check_handoff self-test passed.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Check handoff files and print findings.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when None.

    Returns:
        0 when every handoff passes, 1 on findings, 2 on unreadable input.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return _run_self_test()
    if not args.paths:
        parser.print_usage(sys.stderr)
        return _EXIT_USAGE
    try:
        texts = [(path, path.read_text(encoding="utf-8")) for path in args.paths]
    except (OSError, UnicodeDecodeError) as error:
        print(error, file=sys.stderr)
        return _EXIT_USAGE
    findings = [
        finding
        for path, text in texts
        for finding in check_text(text, shown=path.as_posix())
    ]
    for finding in findings:
        print(finding.render())
    if not findings:
        print(f"Handoffs are complete: {len(texts)} file(s) checked.")
    return _EXIT_FINDINGS if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
