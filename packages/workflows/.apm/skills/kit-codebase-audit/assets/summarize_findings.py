"""Merge SARIF, Ruff JSON and GitLab Code Quality reports into one ranked table.

The script reads report files that analysis tools already wrote; it never runs
a tool, imports project code or uses the network. Accepted inputs:

- SARIF 2.1.0: an object with a ``runs`` list, for example from
  ``ruff check --output-format sarif`` or ``osv-scanner scan --format sarif``.
  The tool name is ``runs[].tool.driver.name``. Results whose ``kind`` is
  ``pass``, ``notApplicable`` or ``informational`` are skipped; a missing
  ``level`` falls back to the rule's ``defaultConfiguration.level`` and then to
  ``warning``.
- Ruff JSON: a list of objects with ``filename``, ``code``, ``location.row`` and
  ``message`` from ``ruff check --output-format json``. A code that starts with
  an ``--error-prefix`` (default ``E9``, ``F63``, ``F7``, ``F82`` and ``S``) or a
  missing code (syntax error) is an ``error``; every other code is a ``warning``.
- GitLab Code Quality JSON: a list of objects with ``check_name``,
  ``description``, ``severity`` and ``location`` (``lines.begin`` or
  ``positions.begin.line``), for example from
  ``ty check --output-format gitlab``. The tool name is the file stem.
  ``info`` is a ``note``, ``minor`` a ``warning``, and ``major``,
  ``critical`` and ``blocker`` are ``error``.

Findings are grouped by tool and rule, then ranked by level (``error``,
``warning``, ``note``), by count, and by tool and rule name, so equal inputs
always produce the same Markdown table.

Exit codes: 0 when no finding remains after ``--min-level``, 1 when findings
remain, 2 on a usage error or a missing, unreadable or malformed report.
``--self-test`` runs built-in regressions on synthetic reports.
"""

import argparse
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote

_DESCRIPTION = "Merge SARIF, Ruff JSON and GitLab Code Quality reports."
_EXIT_FINDINGS = 1
_EXIT_USAGE = 2
_DEFAULT_MAX_LOCATIONS = 3
_MESSAGE_LIMIT = 160
_ELLIPSIS = "..."
_DEFAULT_ERROR_PREFIXES = ("E9", "F63", "F7", "F82", "S")
_SKIPPED_KINDS = frozenset({"pass", "notApplicable", "informational"})
_NO_LOCATION = "(no location)"
_DRIVE_URI = re.compile(r"^/[A-Za-z]:/")


class Level(StrEnum):
    """Normalized finding level, ordered from least to most severe."""

    NOTE = "note"
    WARNING = "warning"
    ERROR = "error"

    @property
    def rank(self) -> int:
        """Return the sort weight; a higher value is more severe."""
        return tuple(Level).index(self)


_SARIF_LEVELS = {
    "none": Level.NOTE,
    "note": Level.NOTE,
    "warning": Level.WARNING,
    "error": Level.ERROR,
}
_GITLAB_LEVELS = {
    "info": Level.NOTE,
    "minor": Level.WARNING,
    "major": Level.ERROR,
    "critical": Level.ERROR,
    "blocker": Level.ERROR,
}


class ReportIssue(StrEnum):
    """Supported report validation failures and their stable messages."""

    OBJECT_REQUIRED = "{where} must be an object"
    LIST_REQUIRED = "{where} must be a list"
    TEXT_REQUIRED = "{where} must be a non-empty string"
    LINE_REQUIRED = "{where} must be a positive integer"
    UNKNOWN_LEVEL = "{where} has an unsupported level"
    UNKNOWN_FORMAT = "{where} is neither SARIF, Ruff JSON nor GitLab Code Quality"


class ReportError(ValueError):
    """A report value violates the accepted input contract."""

    def __init__(self, issue: ReportIssue, *, where: str) -> None:
        """Describe an invalid report value.

        Args:
            issue: The violated input invariant.
            where: Location of the value inside the report.
        """
        super().__init__(issue.value.format(where=where))


class ReportTypeError(TypeError):
    """A report value has the wrong JSON type for the input contract."""

    def __init__(self, issue: ReportIssue, *, where: str) -> None:
        """Describe a report value of the wrong type.

        Args:
            issue: The violated input invariant.
            where: Location of the value inside the report.
        """
        super().__init__(issue.value.format(where=where))


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One normalized finding.

    Args:
        tool: Producing tool, such as ``ruff``.
        rule: Rule identifier reported by the tool.
        level: Normalized level.
        path: Repository-relative path, or ``(no location)``.
        line: One-based line, 0 when unknown.
        message: Tool message.
    """

    tool: str
    rule: str
    level: Level
    path: str
    line: int
    message: str

    @property
    def location(self) -> str:
        """Return ``path:line`` or the bare path when the line is unknown."""
        return f"{self.path}:{self.line}" if self.line else self.path


@dataclass(frozen=True, kw_only=True, slots=True)
class RuleGroup:
    """All findings that share a tool and rule.

    Args:
        tool: Producing tool.
        rule: Rule identifier.
        findings: Findings sorted by location and message.
    """

    tool: str
    rule: str
    findings: tuple[Finding, ...]

    @property
    def level(self) -> Level:
        """Return the most severe level in the group."""
        return max((item.level for item in self.findings), key=lambda lvl: lvl.rank)

    def sort_key(self) -> tuple[int, int, str, str]:
        """Return the ranking key: level, count, tool, rule."""
        return (-self.level.rank, -len(self.findings), self.tool, self.rule)


@dataclass(frozen=True, kw_only=True, slots=True)
class Options:
    """Normalization settings shared by every parser.

    Args:
        root: Path prefix removed from reported paths, or an empty string.
        error_prefixes: Ruff code prefixes treated as ``error``.
    """

    root: str
    error_prefixes: tuple[str, ...]


def _object(value: object, where: str) -> dict[str, object]:
    """Return a JSON object or raise a located type error.

    Raises:
        ReportTypeError: The value is not an object.
    """
    if not isinstance(value, dict):
        raise ReportTypeError(ReportIssue.OBJECT_REQUIRED, where=where)
    return {str(key): item for key, item in value.items()}


def _list(value: object, where: str) -> list[object]:
    """Return a JSON list or raise a located type error.

    Raises:
        ReportTypeError: The value is not a list.
    """
    if not isinstance(value, list):
        raise ReportTypeError(ReportIssue.LIST_REQUIRED, where=where)
    return list(value)


def _text(value: object, where: str) -> str:
    """Return a non-empty string or raise a located error.

    Raises:
        ReportTypeError: The value is not a string.
        ReportError: The string is empty.
    """
    if not isinstance(value, str):
        raise ReportTypeError(ReportIssue.TEXT_REQUIRED, where=where)
    if not value:
        raise ReportError(ReportIssue.TEXT_REQUIRED, where=where)
    return value


def _line(value: object, where: str) -> int:
    """Return a positive line number; ``None`` means unknown and maps to 0.

    Raises:
        ReportTypeError: The value is not an integer.
        ReportError: The line is not positive.
    """
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReportTypeError(ReportIssue.LINE_REQUIRED, where=where)
    if value < 1:
        raise ReportError(ReportIssue.LINE_REQUIRED, where=where)
    return value


def _optional_text(value: object) -> str:
    """Return a string value or an empty string for anything else."""
    return value if isinstance(value, str) else ""


def normalize_path(raw: str, *, root: str) -> str:
    """Return a forward-slash path relative to ``root`` when it is a prefix.

    Args:
        raw: Path or ``file://`` URI as written by the tool.
        root: Prefix to remove; an empty string keeps the path unchanged.

    Returns:
        The normalized path.
    """
    text = unquote(raw.removeprefix("file://")).replace("\\", "/")
    if _DRIVE_URI.match(text):
        text = text.removeprefix("/")
    prefix = root.replace("\\", "/").rstrip("/") + "/"
    if root and text.startswith(prefix):
        return text.removeprefix(prefix)
    return text


def _sarif_location(result: dict[str, object], where: str) -> tuple[str, int]:
    """Return the first physical location of a SARIF result."""
    locations = _list(result.get("locations", []), f"{where}.locations")
    if not locations:
        return _NO_LOCATION, 0
    first = _object(locations[0], f"{where}.locations[0]")
    physical = _object(first.get("physicalLocation", {}), f"{where}.physicalLocation")
    artifact = _object(physical.get("artifactLocation", {}), f"{where}.artifact")
    region = _object(physical.get("region", {}), f"{where}.region")
    uri = artifact.get("uri")
    path = _text(uri, f"{where}.uri") if uri is not None else _NO_LOCATION
    return path, _line(region.get("startLine"), f"{where}.region.startLine")


def _level(raw: object, table: dict[str, Level], where: str) -> Level:
    """Map a tool level string to a normalized level.

    Raises:
        ReportError: The level is unknown.
    """
    level = table.get(_text(raw, where))
    if level is None:
        raise ReportError(ReportIssue.UNKNOWN_LEVEL, where=where)
    return level


def _sarif_rule_levels(driver: dict[str, object], where: str) -> dict[str, str]:
    """Return the default level declared for each SARIF rule identifier."""
    levels: dict[str, str] = {}
    for index, raw in enumerate(_list(driver.get("rules", []), f"{where}.rules")):
        rule = _object(raw, f"{where}.rules[{index}]")
        config = _object(rule.get("defaultConfiguration", {}), f"{where}.config")
        identifier = rule.get("id")
        default = config.get("level")
        if isinstance(identifier, str) and isinstance(default, str):
            levels[identifier] = default
    return levels


def _sarif_result(
    raw: object, *, tool: str, defaults: dict[str, str], where: str, root: str
) -> Finding | None:
    """Normalize one SARIF result, or return ``None`` for a non-failure kind."""
    result = _object(raw, where)
    if result.get("kind") in _SKIPPED_KINDS:
        return None
    rule = _optional_text(result.get("ruleId")) or "unknown"
    level = result.get("level", defaults.get(rule, Level.WARNING.value))
    message = _object(result.get("message", {}), f"{where}.message")
    path, line = _sarif_location(result, where)
    return Finding(
        tool=tool,
        rule=rule,
        level=_level(level, _SARIF_LEVELS, f"{where}.level"),
        path=normalize_path(path, root=root),
        line=line,
        message=_optional_text(message.get("text")),
    )


def parse_sarif(data: dict[str, object], *, options: Options) -> list[Finding]:
    """Normalize every failing result of a SARIF 2.1.0 log.

    Args:
        data: Parsed SARIF log.
        options: Normalization settings.

    Returns:
        Findings in report order.
    """
    findings: list[Finding] = []
    for run_index, raw_run in enumerate(_list(data.get("runs"), "runs")):
        where = f"runs[{run_index}]"
        run = _object(raw_run, where)
        tool = _object(run.get("tool"), f"{where}.tool")
        driver = _object(tool.get("driver"), f"{where}.tool.driver")
        name = _text(driver.get("name"), f"{where}.tool.driver.name")
        defaults = _sarif_rule_levels(driver, f"{where}.tool.driver")
        results = _list(run.get("results", []), f"{where}.results")
        for index, raw in enumerate(results):
            finding = _sarif_result(
                raw,
                tool=name,
                defaults=defaults,
                where=f"{where}.results[{index}]",
                root=options.root,
            )
            if finding is not None:
                findings.append(finding)
    return findings


def _ruff_item(item: dict[str, object], *, where: str, options: Options) -> Finding:
    """Normalize one Ruff JSON diagnostic."""
    code = _optional_text(item.get("code"))
    location = _object(item.get("location", {}), f"{where}.location")
    is_error = not code or code.startswith(options.error_prefixes)
    return Finding(
        tool="ruff",
        rule=code or "syntax-error",
        level=Level.ERROR if is_error else Level.WARNING,
        path=normalize_path(_text(item.get("filename"), where), root=options.root),
        line=_line(location.get("row"), f"{where}.location.row"),
        message=_optional_text(item.get("message")),
    )


def _gitlab_line(location: dict[str, object], where: str) -> int:
    """Return ``lines.begin`` or ``positions.begin.line`` of a GitLab issue."""
    if "positions" in location:
        positions = _object(location["positions"], f"{where}.positions")
        begin = _object(positions.get("begin", {}), f"{where}.positions.begin")
        return _line(begin.get("line"), f"{where}.positions.begin.line")
    lines = _object(location.get("lines", {}), f"{where}.lines")
    return _line(lines.get("begin"), f"{where}.lines.begin")


def _gitlab_item(
    item: dict[str, object], *, tool: str, where: str, options: Options
) -> Finding:
    """Normalize one GitLab Code Quality issue."""
    location = _object(item.get("location"), f"{where}.location")
    return Finding(
        tool=tool,
        rule=_text(item.get("check_name"), f"{where}.check_name"),
        level=_level(item.get("severity"), _GITLAB_LEVELS, f"{where}.severity"),
        path=normalize_path(
            _text(location.get("path"), f"{where}.path"), root=options.root
        ),
        line=_gitlab_line(location, f"{where}.location"),
        message=_optional_text(item.get("description")),
    )


def parse_list_report(
    data: list[object], *, tool: str, options: Options
) -> list[Finding]:
    """Normalize a Ruff JSON or GitLab Code Quality list, detected per item.

    Args:
        data: Parsed JSON list.
        tool: Tool name used for GitLab Code Quality items.
        options: Normalization settings.

    Returns:
        Findings in report order.

    Raises:
        ReportError: An item matches neither list format.
    """
    findings: list[Finding] = []
    for index, raw in enumerate(data):
        where = f"[{index}]"
        item = _object(raw, where)
        if "check_name" in item:
            findings.append(_gitlab_item(item, tool=tool, where=where, options=options))
        elif "filename" in item:
            findings.append(_ruff_item(item, where=where, options=options))
        else:
            raise ReportError(ReportIssue.UNKNOWN_FORMAT, where=where)
    return findings


def parse_document(data: object, *, tool: str, options: Options) -> list[Finding]:
    """Normalize one parsed report document of any accepted format.

    Args:
        data: Parsed JSON document.
        tool: Tool name used for GitLab Code Quality items.
        options: Normalization settings.

    Returns:
        Findings in report order.

    Raises:
        ReportError: The document matches no accepted format.
    """
    if isinstance(data, dict) and "runs" in data:
        return parse_sarif(_object(data, "report"), options=options)
    if isinstance(data, list):
        return parse_list_report(list(data), tool=tool, options=options)
    raise ReportError(ReportIssue.UNKNOWN_FORMAT, where="report")


def load_report(path: Path, *, options: Options) -> list[Finding]:
    """Read one report file and normalize its findings.

    Args:
        path: SARIF, Ruff JSON or GitLab Code Quality file.
        options: Normalization settings.

    Returns:
        Findings in report order.
    """
    data: object = json.loads(path.read_text(encoding="utf-8"))
    return parse_document(data, tool=path.stem, options=options)


def rank(findings: Iterable[Finding], *, min_level: Level) -> list[RuleGroup]:
    """Group findings by tool and rule and rank the groups.

    Args:
        findings: Normalized findings from every report.
        min_level: Least severe level kept.

    Returns:
        Groups ordered by level, count, tool and rule.
    """
    grouped: dict[tuple[str, str], list[Finding]] = {}
    for item in findings:
        if item.level.rank >= min_level.rank:
            grouped.setdefault((item.tool, item.rule), []).append(item)
    groups = [
        RuleGroup(
            tool=tool,
            rule=rule,
            findings=tuple(
                sorted(items, key=lambda f: (f.path, f.line, f.message, f.level))
            ),
        )
        for (tool, rule), items in grouped.items()
    ]
    return sorted(groups, key=RuleGroup.sort_key)


def _cell(text: str) -> str:
    """Return text that is safe inside one Markdown table cell."""
    flat = " ".join(text.split()).replace("|", "\\|")
    if len(flat) > _MESSAGE_LIMIT:
        return flat[: _MESSAGE_LIMIT - len(_ELLIPSIS)] + _ELLIPSIS
    return flat


def _locations(group: RuleGroup, *, max_locations: int) -> str:
    """Render the first distinct locations of a group and the remainder."""
    unique = list(dict.fromkeys(item.location for item in group.findings))
    shown = ", ".join(f"`{location}`" for location in unique[:max_locations])
    hidden = len(unique) - max_locations
    return f"{shown}, +{hidden} more" if hidden > 0 else shown


def render(groups: Sequence[RuleGroup], *, max_locations: int) -> str:
    """Render ranked groups as a Markdown table followed by a summary line.

    Args:
        groups: Ranked groups from ``rank``.
        max_locations: Distinct locations listed per group.

    Returns:
        Markdown text ending with a newline.
    """
    total = sum(len(group.findings) for group in groups)
    tools = len({group.tool for group in groups})
    summary = f"{total} finding(s) in {len(groups)} rule group(s) from {tools} tool(s)."
    if not groups:
        return summary + "\n"
    lines = [
        "| Rank | Level | Tool | Rule | Count | Locations | Message |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for position, group in enumerate(groups, start=1):
        cells = (
            str(position),
            group.level.value,
            _cell(group.tool),
            f"`{_cell(group.rule)}`",
            str(len(group.findings)),
            _locations(group, max_locations=max_locations),
            _cell(group.findings[0].message),
        )
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join([*lines, "", summary]) + "\n"


_SELF_TEST_OPTIONS = Options(root="/repo", error_prefixes=_DEFAULT_ERROR_PREFIXES)
_SELF_TEST_SARIF = {
    "version": "2.1.0",
    "runs": [
        {
            "tool": {
                "driver": {
                    "name": "scanner",
                    "rules": [
                        {"id": "GHSA-1", "defaultConfiguration": {"level": "error"}}
                    ],
                }
            },
            "results": [
                {
                    "ruleId": "GHSA-1",
                    "message": {"text": "vulnerable | package"},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": "file:///repo/uv.lock"},
                                "region": {"startLine": 1},
                            }
                        }
                    ],
                },
                {"ruleId": "PASS-1", "kind": "pass"},
                {"ruleId": "R1", "level": "note"},
            ],
        }
    ],
}
_SELF_TEST_LIST = [
    {"code": "C901", "filename": "/repo/src/b.py", "location": {"row": 1}},
    {"code": "C901", "filename": "/repo/src/a.py", "location": {"row": 1}},
    {
        "check_name": "invalid-assignment",
        "severity": "minor",
        "location": {"path": "src/a.py", "positions": {"begin": {"line": 1}}},
    },
]
_SELF_TEST_EXPECTED = [
    "| 1 | error | scanner | `GHSA-1` | 1 | `uv.lock:1` | vulnerable \\| package |",
    "| 2 | warning | ruff | `C901` | 2 | `src/a.py:1`, +1 more |  |",
    "| 3 | warning | ty | `invalid-assignment` | 1 | `src/a.py:1` |  |",
    "| 4 | note | scanner | `R1` | 1 | `(no location)` |  |",
]
_TABLE_HEADER_ROWS = 2
_TABLE_FOOTER_ROWS = 2
_SELF_TEST_BROKEN = (
    {"runs": {}},
    {"runs": [{"tool": {"driver": {}}}]},
    [{"other": 1}],
    [{"filename": "a.py", "location": {"row": 0}}],
    "text",
)


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by ``--self-test``."""

    RANKING = "ranked table rows differ from the expected rows"
    MALFORMED_ACCEPTED = "malformed report accepted: {case}"


class SelfTestError(RuntimeError):
    """A documented self-test invariant failed."""

    def __init__(self, issue: SelfTestIssue, *, case: str = "") -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
            case: Input that exposed the failure, when relevant.
        """
        super().__init__(issue.value.format(case=case))


def self_test() -> None:
    """Exercise parsing, ranking, rendering and malformed input.

    Raises:
        SelfTestError: A documented behavior regressed.
    """
    findings = [
        *parse_document(_SELF_TEST_SARIF, tool="unused", options=_SELF_TEST_OPTIONS),
        *parse_document(_SELF_TEST_LIST, tool="ty", options=_SELF_TEST_OPTIONS),
    ]
    rows = render(rank(findings, min_level=Level.NOTE), max_locations=1).splitlines()
    if rows[_TABLE_HEADER_ROWS:-_TABLE_FOOTER_ROWS] != _SELF_TEST_EXPECTED:
        raise SelfTestError(SelfTestIssue.RANKING)
    for broken in _SELF_TEST_BROKEN:
        try:
            parse_document(broken, tool="x", options=_SELF_TEST_OPTIONS)
        except (ReportError, ReportTypeError):
            continue
        raise SelfTestError(SelfTestIssue.MALFORMED_ACCEPTED, case=repr(broken))


def _positive(text: str) -> int:
    """Parse a positive integer command-line value.

    Raises:
        argparse.ArgumentTypeError: The value is not a positive integer.
    """
    value = int(text)
    if value < 1:
        message = "must be a positive integer"
        raise argparse.ArgumentTypeError(message)
    return value


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=_DESCRIPTION)
    parser.add_argument("reports", nargs="*", type=Path, help="report files")
    parser.add_argument("--root", default="", help="path prefix to remove")
    parser.add_argument(
        "--min-level", choices=[level.value for level in Level], default="note"
    )
    parser.add_argument(
        "--max-locations", type=_positive, default=_DEFAULT_MAX_LOCATIONS
    )
    parser.add_argument(
        "--error-prefix",
        action="append",
        dest="error_prefixes",
        help="Ruff code prefix treated as error (repeatable; replaces defaults)",
    )
    parser.add_argument("--output", type=Path, help="write Markdown here")
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in regressions"
    )
    return parser


def _summarize(args: argparse.Namespace) -> int:
    """Merge the reports named in parsed arguments and emit the table."""
    options = Options(
        root=args.root,
        error_prefixes=tuple(args.error_prefixes or _DEFAULT_ERROR_PREFIXES),
    )
    findings: list[Finding] = []
    for path in args.reports:
        try:
            findings.extend(load_report(path, options=options))
        except (OSError, ValueError, TypeError) as error:
            print(f"{path}: {error}", file=sys.stderr)
            return _EXIT_USAGE
    groups = rank(findings, min_level=Level(args.min_level))
    text = render(groups, max_locations=args.max_locations)
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.write_text(text, encoding="utf-8")
    return _EXIT_FINDINGS if groups else 0


def _run_self_test() -> int:
    """Run the self-test, print its outcome and return the exit status."""
    try:
        self_test()
    except SelfTestError as error:
        print(f"summarize_findings self-test failed: {error}", file=sys.stderr)
        return _EXIT_FINDINGS
    print("summarize_findings self-test passed.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Merge reports and print or write the ranked table.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv``.

    Returns:
        0 when clean, 1 when findings remain, 2 on usage or input errors.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return _run_self_test()
    if not args.reports:
        parser.error("at least one report file is required")
    return _summarize(args)


if __name__ == "__main__":
    sys.exit(main())
