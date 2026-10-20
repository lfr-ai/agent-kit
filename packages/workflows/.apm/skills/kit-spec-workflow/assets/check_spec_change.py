"""Validate a spec-driven change folder before review, verification or archive.

The checker reads Markdown only and never executes or imports consumer files.
It enforces the folder contract described in 'references/lifecycle.md':
required files exist and are nonempty, every active requirement has at least
one Given/When/Then scenario, tasks are checkbox items, the declared status is
consistent with task completion and the verification report, and no unresolved
placeholder markers remain outside fenced code blocks.
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

_DEFAULT_REQUIRED = ("proposal.md", "requirements.md", "tasks.md")
_DEFAULT_MARKERS = ("TODO", "TBD", "FIXME", "XXX")
_DEFAULT_ID_PATTERN = r"REQ-\d{3,}"
_STATUSES = (
    "draft",
    "proposed",
    "specified",
    "planned",
    "applying",
    "verified",
    "archived",
)
_CLOSED_STATUSES = frozenset({"verified", "archived"})
_CHANGE_KINDS = frozenset({"add", "modify", "remove"})
_NORMATIVE = re.compile(r"\b(?:MUST|SHALL|SHOULD|MAY)\b")
_FENCE = re.compile(r"^\s*(```|~~~)")
_STATUS = re.compile(r"^(?:[-*+]\s+)?\**Status\**\s*:\s*\**\s*([A-Za-z-]+)")
_RESULT = re.compile(r"^(?:[-*+]\s+)?\**Result\**\s*:\s*\**\s*([A-Za-z-]+)")
_CHANGE = re.compile(r"^(?:[-*+]\s+)?\**Change\**\s*:\s*\**\s*([A-Za-z-]+)")
_REASON = re.compile(r"^(?:[-*+]\s+)?\**Reason\**\s*:\s*\S")
_SCENARIO = re.compile(r"^###\s+Scenario:\s*(\S.*)$")
_STEP = re.compile(r"^(?:[-*+]\s+)?\**(Given|When|Then|And|But)\b\**\s+\S")
_CHECKBOX = re.compile(r"^\s*[-*+]\s+\[([ xX])\]\s+\S")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One located defect in a change folder.

    Args:
        path: File that holds the defect, or the expected file when missing.
        line: One-based line number; 1 when the defect concerns a whole file.
        message: Human-readable description of the defect.
    """

    path: Path
    line: int
    message: str

    def render(self) -> str:
        """Return the deterministic 'path:line: message' form."""
        return f"{self.path.as_posix()}:{self.line}: {self.message}"


@dataclass(frozen=True, kw_only=True, slots=True)
class Settings:
    """Configurable names and markers for one validation run.

    Args:
        required: File names that must exist and be nonempty.
        spec_name: File name that holds requirements and scenarios.
        tasks_name: File name that holds the checkbox task list.
        proposal_name: File name that declares the change status.
        verification_name: File name of the verification report.
        markers: Whole-word placeholder markers that block completion.
        id_pattern: Regular expression for requirement identifiers.
        trace: Require every active requirement identifier in the task list.
    """

    required: tuple[str, ...] = _DEFAULT_REQUIRED
    spec_name: str = "requirements.md"
    tasks_name: str = "tasks.md"
    proposal_name: str = "proposal.md"
    verification_name: str = "verification.md"
    markers: tuple[str, ...] = _DEFAULT_MARKERS
    id_pattern: str = _DEFAULT_ID_PATTERN
    trace: bool = False


@dataclass(frozen=True, kw_only=True, slots=True)
class Requirement:
    """A parsed requirement section.

    Args:
        identifier: Requirement identifier such as 'REQ-001'.
        line: One-based line of the requirement heading.
        kind: Declared change kind: 'add', 'modify' or 'remove'.
        normative: Whether the statement uses a normative keyword.
        has_reason: Whether a 'Reason:' line is present.
        scenarios: Parsed scenarios as (name, line, step keywords) tuples.
    """

    identifier: str
    line: int
    kind: str
    normative: bool
    has_reason: bool
    scenarios: tuple[tuple[str, int, tuple[str, ...]], ...]


@dataclass(kw_only=True, slots=True)
class _Draft:
    """Mutable requirement under construction while scanning lines."""

    identifier: str
    line: int
    kind: str = "add"
    normative: bool = False
    has_reason: bool = False
    scenarios: list[tuple[str, int, list[str]]] = field(default_factory=list)

    def consume(self, number: int, line: str) -> None:
        """Record one stripped prose line that belongs to this requirement."""
        if scenario := _SCENARIO.match(line):
            self.scenarios.append((scenario.group(1).strip(), number, []))
        elif self.scenarios:
            if step := _STEP.match(line):
                self.scenarios[-1][2].append(step.group(1))
        else:
            if kind := _CHANGE.match(line):
                self.kind = kind.group(1).casefold()
            self.has_reason = self.has_reason or bool(_REASON.match(line))
            self.normative = self.normative or bool(_NORMATIVE.search(line))

    def freeze(self) -> Requirement:
        """Return the immutable requirement record."""
        return Requirement(
            identifier=self.identifier,
            line=self.line,
            kind=self.kind,
            normative=self.normative,
            has_reason=self.has_reason,
            scenarios=tuple(
                (name, line, tuple(steps)) for name, line, steps in self.scenarios
            ),
        )


def _prose_lines(text: str) -> list[tuple[int, str]]:
    """Return numbered lines outside fenced code blocks.

    Args:
        text: Markdown document text.

    Returns:
        One-based line numbers paired with line text, excluding fenced code.
    """
    lines: list[tuple[int, str]] = []
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            lines.append((number, line))
    return lines


def parse_requirements(text: str, id_pattern: str) -> list[Requirement]:
    """Parse '## <id> title' sections and their '### Scenario:' blocks.

    Args:
        text: Requirements document text.
        id_pattern: Regular expression for requirement identifiers.

    Returns:
        Requirements in document order.
    """
    heading = re.compile(rf"^##\s+({id_pattern})\b")
    drafts: list[_Draft] = []
    current: _Draft | None = None
    for number, line in _prose_lines(text):
        match = heading.match(line)
        if match or line.startswith("## "):
            current = _Draft(identifier=match.group(1), line=number) if match else None
            if current is not None:
                drafts.append(current)
            continue
        if current is not None:
            current.consume(number, line.strip())
    return [draft.freeze() for draft in drafts]


def _requirement_findings(path: Path, requirement: Requirement) -> list[Finding]:
    """Check one requirement's change kind, wording and scenarios."""
    findings: list[Finding] = []

    def add(line: int, message: str) -> None:
        findings.append(Finding(path=path, line=line, message=message))

    label = requirement.identifier
    if requirement.kind not in _CHANGE_KINDS:
        add(requirement.line, f"{label}: unknown change kind '{requirement.kind}'")
    if requirement.kind == "remove":
        if not requirement.has_reason:
            add(requirement.line, f"{label}: removed requirement needs a Reason line")
        return findings
    if not requirement.normative:
        add(
            requirement.line,
            f"{label}: statement lacks a normative keyword (MUST/SHALL/SHOULD/MAY)",
        )
    if not requirement.scenarios:
        add(requirement.line, f"{label}: requirement has no scenario")
    names: set[str] = set()
    for name, line, steps in requirement.scenarios:
        if name.casefold() in names:
            add(line, f"{label}: duplicate scenario name '{name}'")
        names.add(name.casefold())
        for keyword in ("When", "Then"):
            if keyword not in steps:
                add(line, f"{label}: scenario '{name}' has no {keyword} step")
        if steps and steps[0] in {"And", "But"}:
            add(line, f"{label}: scenario '{name}' starts with {steps[0]}")
    return findings


def check_requirements(path: Path, text: str, id_pattern: str) -> list[Finding]:
    """Validate requirement identifiers, wording and scenario coverage.

    Args:
        path: Requirements file used in findings.
        text: Requirements document text.
        id_pattern: Regular expression for requirement identifiers.

    Returns:
        Findings in line order.
    """
    requirements = parse_requirements(text, id_pattern)
    if not requirements:
        return [Finding(path=path, line=1, message="no requirement sections found")]
    findings: list[Finding] = []
    seen: dict[str, int] = {}
    for requirement in requirements:
        if requirement.identifier in seen:
            findings.append(
                Finding(
                    path=path,
                    line=requirement.line,
                    message=(
                        f"{requirement.identifier}: duplicate identifier "
                        f"(first on line {seen[requirement.identifier]})"
                    ),
                )
            )
        seen.setdefault(requirement.identifier, requirement.line)
        findings.extend(_requirement_findings(path, requirement))
    return findings


def check_tasks(path: Path, text: str) -> tuple[list[Finding], int]:
    """Require every list item to be a checkbox and count open tasks.

    Args:
        path: Task file used in findings.
        text: Task document text.

    Returns:
        Findings and the number of unchecked tasks.
    """
    findings: list[Finding] = []
    total = 0
    open_tasks = 0
    for number, line in _prose_lines(text):
        checkbox = _CHECKBOX.match(line)
        if checkbox:
            total += 1
            open_tasks += checkbox.group(1) == " "
        elif _LIST_ITEM.match(line):
            findings.append(
                Finding(path=path, line=number, message="list item is not a checkbox")
            )
    if not total:
        findings.append(Finding(path=path, line=1, message="no checkbox tasks found"))
    return findings, open_tasks


def check_markers(path: Path, text: str, markers: tuple[str, ...]) -> list[Finding]:
    """Report unresolved placeholder markers outside fenced code.

    Args:
        path: File used in findings.
        text: Document text.
        markers: Whole-word, case-sensitive markers.

    Returns:
        One finding per line that contains a marker.
    """
    if not markers:
        return []
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, markers)) + r")\b")
    return [
        Finding(path=path, line=number, message=f"unresolved marker '{match.group(1)}'")
        for number, line in _prose_lines(text)
        if (match := pattern.search(line))
    ]


def _first_value(text: str, pattern: re.Pattern[str]) -> tuple[str, int] | None:
    """Return the first captured value and its line, outside code fences."""
    for number, line in _prose_lines(text):
        if match := pattern.match(line.strip()):
            return match.group(1).casefold(), number
    return None


def _status_findings(
    directory: Path, settings: Settings, open_tasks: int | None
) -> list[Finding]:
    """Check that the declared status matches tasks and verification evidence."""
    proposal = directory / settings.proposal_name
    if not proposal.is_file():
        return []
    status = _first_value(proposal.read_text(encoding="utf-8"), _STATUS)
    if status is None:
        return [Finding(path=proposal, line=1, message="no 'Status:' line declared")]
    value, line = status
    if value not in _STATUSES:
        allowed = ", ".join(_STATUSES)
        return [
            Finding(
                path=proposal,
                line=line,
                message=f"unknown status '{value}' (expected one of: {allowed})",
            )
        ]
    if value not in _CLOSED_STATUSES:
        return []
    findings: list[Finding] = []
    if open_tasks:
        findings.append(
            Finding(
                path=proposal,
                line=line,
                message=f"status '{value}' with {open_tasks} unchecked task(s)",
            )
        )
    report = directory / settings.verification_name
    result = (
        _first_value(report.read_text(encoding="utf-8"), _RESULT)
        if report.is_file()
        else None
    )
    if result is None or result[0] != "pass":
        findings.append(
            Finding(
                path=report,
                line=result[1] if result else 1,
                message=f"status '{value}' requires a verification 'Result: pass'",
            )
        )
    return findings


def _trace_findings(
    spec: Path, tasks_text: str, tasks: Path, settings: Settings
) -> list[Finding]:
    """Require each active requirement identifier to appear in the task list."""
    requirements = parse_requirements(
        spec.read_text(encoding="utf-8"), settings.id_pattern
    )
    return [
        Finding(
            path=tasks,
            line=1,
            message=f"{item.identifier}: no task references this requirement",
        )
        for item in requirements
        if item.kind != "remove"
        and not re.search(rf"\b{re.escape(item.identifier)}\b", tasks_text)
    ]


def check_change(directory: Path, settings: Settings | None = None) -> list[Finding]:
    """Validate one change folder against the lifecycle contract.

    Args:
        directory: Change folder to validate.
        settings: Names, markers and options; defaults when omitted.

    Returns:
        Findings sorted by path and line.

    Raises:
        OSError: A file exists but cannot be read.
        UnicodeError: A file is not valid UTF-8.
    """
    options = settings or Settings()
    if not directory.is_dir():
        return [Finding(path=directory, line=1, message="change folder not found")]
    findings: list[Finding] = []
    for name in options.required:
        path = directory / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            findings.append(
                Finding(path=path, line=1, message="missing or empty required file")
            )
    spec = directory / options.spec_name
    if spec.is_file():
        findings.extend(
            check_requirements(
                spec, spec.read_text(encoding="utf-8"), options.id_pattern
            )
        )
    tasks = directory / options.tasks_name
    open_tasks: int | None = None
    if tasks.is_file():
        tasks_text = tasks.read_text(encoding="utf-8")
        task_findings, open_tasks = check_tasks(tasks, tasks_text)
        findings.extend(task_findings)
        if options.trace and spec.is_file():
            findings.extend(_trace_findings(spec, tasks_text, tasks, options))
    for document in sorted(directory.rglob("*.md")):
        findings.extend(
            check_markers(
                document, document.read_text(encoding="utf-8"), options.markers
            )
        )
    findings.extend(_status_findings(directory, options, open_tasks))
    return sorted(
        set(findings), key=lambda item: (item.path.as_posix(), item.line, item.message)
    )


_VALID_FILES = {
    "proposal.md": "# Add invoice export\n\nStatus: verified\n\nWhy: finance needs CSV.\n",
    "requirements.md": (
        "# Requirements\n\n## REQ-001 Export invoices\n\n"
        "The service MUST export invoices of one month as CSV.\n\n"
        "### Scenario: Month with invoices\n\n"
        "- Given two invoices dated in March\n"
        "- When the user exports March\n"
        "- Then the file has a header and two rows\n\n"
        "## REQ-002 Legacy XML export\n\nChange: remove\n"
        "Reason: replaced by REQ-001.\n"
    ),
    "tasks.md": "# Tasks\n\n- [x] 1.1 Add CSV writer for REQ-001\n",
    "verification.md": "# Verification\n\nResult: pass\n",
}


class MissingFindingError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(self, *, expected: str) -> None:
        """Describe the violated invariant.

        Args:
            expected: Diagnostic expected for the failing input.
        """
        super().__init__(f"missing finding: {expected}")


def self_test() -> None:
    """Exercise passing and failing synthetic change folders.

    Raises:
        AssertionError: A rule does not behave as documented.
    """
    with TemporaryDirectory(prefix="spec-change-") as raw:
        change = Path(raw) / "add-invoice-export"
        change.mkdir()
        for name, text in _VALID_FILES.items():
            (change / name).write_text(text, encoding="utf-8")
        if findings := check_change(change, Settings(trace=True)):
            raise AssertionError([item.render() for item in findings])
        (change / "tasks.md").write_text(
            "- [ ] Add CSV writer\n- write docs\n", encoding="utf-8"
        )
        (change / "requirements.md").write_text(
            "## REQ-001 Export\n\nExports invoices. TBD\n", encoding="utf-8"
        )
        messages = " ".join(item.message for item in check_change(change))
        for expected in (
            "not a checkbox",
            "no scenario",
            "normative keyword",
            "unresolved marker",
            "unchecked task",
        ):
            if expected not in messages:
                raise MissingFindingError(expected=expected)


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("changes", nargs="*", type=Path, help="change folders")
    parser.add_argument(
        "--required",
        action="append",
        default=[],
        help="required file name (repeatable; replaces the default set)",
    )
    parser.add_argument("--spec-name", default="requirements.md")
    parser.add_argument("--tasks-name", default="tasks.md")
    parser.add_argument("--proposal-name", default="proposal.md")
    parser.add_argument("--verification-name", default="verification.md")
    parser.add_argument(
        "--marker",
        action="append",
        default=[],
        help="placeholder marker (repeatable; replaces the default set)",
    )
    parser.add_argument("--id-pattern", default=_DEFAULT_ID_PATTERN)
    parser.add_argument(
        "--trace",
        action="store_true",
        help="require each active requirement identifier in the task list",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate change folders and print one finding per line.

    Args:
        argv: Command-line arguments; 'sys.argv' when omitted.

    Returns:
        0 when every folder passes, 1 on findings, 2 on unusable input.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("check_spec_change self-test passed.")
        return 0
    if not args.changes:
        parser.print_usage(sys.stderr)
        return 2
    try:
        re.compile(args.id_pattern)
    except re.error as error:
        print(f"invalid --id-pattern: {error}", file=sys.stderr)
        return 2
    settings = Settings(
        required=tuple(args.required) or _DEFAULT_REQUIRED,
        spec_name=args.spec_name,
        tasks_name=args.tasks_name,
        proposal_name=args.proposal_name,
        verification_name=args.verification_name,
        markers=tuple(args.marker) or _DEFAULT_MARKERS,
        id_pattern=args.id_pattern,
        trace=args.trace,
    )
    findings: list[Finding] = []
    try:
        for change in args.changes:
            findings.extend(check_change(change, settings))
    except (OSError, UnicodeError) as error:
        print(f"cannot read change: {error}", file=sys.stderr)
        return 2
    for finding in findings:
        print(finding.render())
    if not findings:
        print(f"{len(args.changes)} change folder(s) passed.")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
