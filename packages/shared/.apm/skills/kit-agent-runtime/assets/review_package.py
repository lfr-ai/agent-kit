"""Assemble a reviewer-ready Markdown package from a diff and verification evidence.

Inputs are a unified diff file (for example the output of 'git diff --no-color' or
'git diff --cached --no-color') and a JSON file describing the task, acceptance
criteria, executed verification commands, and known limitations. The script never
runs git or the verification commands itself: it packages evidence that the worker
already produced so the reviewer can check it.

Gate findings are printed to stderr as 'path:line: message' and make the exit code
1: a failed or missing verification command, an unmet acceptance criterion, an
empty diff, or a changed file outside the '--allow' path prefixes. Exit code 2 means
the inputs could not be read.
"""

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import TextIO

_CONFIG_EXIT = 2
_DEFAULT_MAX_BYTES = 5 * 1024 * 1024
_EVIDENCE_FIELDS = frozenset(
    {"task", "worker", "summary", "acceptance", "commands", "limitations", "follow_up"}
)
_ACCEPTANCE_FIELDS = frozenset({"criterion", "status", "evidence"})
_COMMAND_FIELDS = frozenset({"command", "exit_code", "summary"})
_STATUSES = ("met", "partial", "unmet", "not-applicable")
_HUNK = re.compile(r"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


@dataclass(kw_only=True, slots=True)
class FileChange:
    """One file in the diff with its change kind and line counts."""

    path: str
    status: str = "modified"
    added: int = 0
    removed: int = 0
    binary: bool = False
    line: int = 1
    old_path: str | None = None


@dataclass(frozen=True, kw_only=True, slots=True)
class Command:
    """One verification command and its recorded outcome."""

    command: str
    exit_code: int
    summary: str


@dataclass(frozen=True, kw_only=True, slots=True)
class Criterion:
    """One acceptance criterion with status and supporting evidence."""

    criterion: str
    status: str
    evidence: str


@dataclass(frozen=True, kw_only=True, slots=True)
class Evidence:
    """Validated worker evidence for one task."""

    task: str
    worker: str
    summary: str
    acceptance: tuple[Criterion, ...]
    commands: tuple[Command, ...]
    limitations: tuple[str, ...]
    follow_up: tuple[str, ...]


@dataclass(kw_only=True, slots=True)
class _DiffState:
    """Mutable parser state while reading one diff."""

    files: list[FileChange] = field(default_factory=list)
    current: FileChange | None = None
    header_open: bool = False
    old_left: int = 0
    new_left: int = 0


def _strip_prefix(raw: str) -> str | None:
    """Return a repository path from a diff header path, or None for /dev/null."""
    text = raw.strip().split("\t", 1)[0]
    if len(text) >= 2 and text[0] == text[-1] == '"':  # noqa: PLR2004
        text = text[1:-1]
    if text == "/dev/null":
        return None
    if text.startswith(("a/", "b/")):
        return text[2:]
    return text


def _git_header_path(line: str) -> str:
    """Read the destination path from a 'diff --git a/x b/y' header."""
    rest = line[len("diff --git ") :]
    marker = rest.rfind(" b/")
    if marker >= 0:
        return rest[marker + 3 :].strip().strip('"')
    return rest.split(" ")[-1].strip('"')


def _start(state: _DiffState, path: str, line: int) -> FileChange:
    """Begin a new file entry with an open header."""
    change = FileChange(path=path, line=line)
    state.files.append(change)
    state.current = change
    state.header_open = True
    return change


def _extended_header(change: FileChange, line: str) -> None:
    """Apply a git extended header line such as a mode, rename, or binary marker."""
    if line.startswith("new file mode"):
        change.status = "added"
    elif line.startswith("deleted file mode"):
        change.status = "deleted"
    elif line.startswith("rename from "):
        change.status = "renamed"
        change.old_path = line[len("rename from ") :]
    elif line.startswith("rename to "):
        change.path = line[len("rename to ") :]
    elif line.startswith(("Binary files ", "GIT binary patch")):
        change.binary = True


def _hunk_line(state: _DiffState, change: FileChange, line: str) -> None:
    """Count one hunk body line and close the hunk when its ranges are consumed."""
    if line.startswith("+"):
        change.added += 1
        state.new_left -= 1
    elif line.startswith("-"):
        change.removed += 1
        state.old_left -= 1
    elif not line.startswith("\\"):
        state.old_left -= 1
        state.new_left -= 1


def parse_diff(text: str) -> list[FileChange]:
    """Parse git or plain unified diff text into per-file changes."""
    state = _DiffState()
    for number, line in enumerate(text.splitlines(), start=1):
        change = state.current
        in_hunk = state.old_left > 0 or state.new_left > 0
        if in_hunk and line and line[0] not in " +-\\":
            state.old_left = state.new_left = 0
            in_hunk = False
        if in_hunk and change is not None:
            _hunk_line(state, change, line)
        elif line.startswith("diff --git "):
            _start(state, _git_header_path(line), number)
        elif line.startswith("--- "):
            source = _strip_prefix(line[4:])
            if change is None or not state.header_open:
                change = _start(state, source or "/dev/null", number)
            if source is None:
                change.status = "added"
        elif line.startswith("+++ ") and change is not None:
            target = _strip_prefix(line[4:])
            if target is None:
                change.status = "deleted"
            else:
                change.path = target
            state.header_open = False
        elif line.startswith("@@") and change is not None:
            match = _HUNK.match(line)
            state.old_left = int(match.group(1) or 1) if match else 0
            state.new_left = int(match.group(2) or 1) if match else 0
            state.header_open = False
        elif change is not None and state.header_open:
            _extended_header(change, line)
    return state.files


class EvidenceInputIssue(StrEnum):
    """Supported evidence input validation failures and their stable messages."""

    TEXT_REQUIRED = "{label} must be non-empty text"
    LIST_REQUIRED = "{label} must be a list"
    OBJECT_REQUIRED = "{label} must be an object"
    UNKNOWN_FIELD = "{label} has unknown field '{field}'"
    EXIT_CODE = "commands[{index}].exit_code must be an integer"
    ACCEPTANCE_STATUS = f"acceptance[{{index}}].status must be one of {list(_STATUSES)}"
    FILE_SIZE = "{path} exceeds {limit} bytes"


class EvidenceInputError(ValueError):
    """An input violates the evidence input contract."""

    def __init__(
        self,
        issue: EvidenceInputIssue,
        *,
        label: str | None = None,
        field: str | None = None,
        index: int | None = None,
        path: Path | None = None,
        limit: int | None = None,
    ) -> None:
        """Describe a supported input failure.

        Args:
            issue: The violated input invariant.
            label: Diagnostic label for the invalid input.
            field: Diagnostic field for the invalid input.
            index: Diagnostic index for the invalid input.
            path: Diagnostic path for the invalid input.
            limit: Diagnostic limit for the invalid input.
        """
        super().__init__(
            issue.value.format(
                label=label, field=field, index=index, path=path, limit=limit
            )
        )


class EvidenceInputTypeError(TypeError):
    """An input has the wrong Python type for the evidence input contract."""

    def __init__(
        self,
        issue: EvidenceInputIssue,
        *,
        label: str | None = None,
        index: int | None = None,
    ) -> None:
        """Describe a wrong input type.

        Args:
            issue: The violated input invariant.
            label: Diagnostic label for the invalid input.
            index: Diagnostic index for the invalid input.
        """
        super().__init__(issue.value.format(label=label, index=index))


def _text(value: object, label: str, *, required: bool = True) -> str:
    """Validate a text field."""
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise EvidenceInputTypeError(EvidenceInputIssue.TEXT_REQUIRED, label=label)
    if required and not value.strip():
        raise EvidenceInputError(EvidenceInputIssue.TEXT_REQUIRED, label=label)
    return value.strip()


def _required_text(item: dict[str, object], key: str, label: str) -> str:
    """Distinguish a missing field from a present value of the wrong type."""
    if key not in item:
        raise EvidenceInputError(EvidenceInputIssue.TEXT_REQUIRED, label=label)
    return _text(item[key], label)


def _items(value: object, label: str) -> list[object]:
    """Validate an optional list field."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise EvidenceInputTypeError(EvidenceInputIssue.LIST_REQUIRED, label=label)
    return value


def _closed(value: object, fields: frozenset[str], label: str) -> dict[str, object]:
    """Require an object with only known fields."""
    if not isinstance(value, dict):
        raise EvidenceInputTypeError(EvidenceInputIssue.OBJECT_REQUIRED, label=label)
    unknown = sorted(value.keys() - fields)
    if unknown:
        raise EvidenceInputError(
            EvidenceInputIssue.UNKNOWN_FIELD, label=label, field=unknown[0]
        )
    return value


def parse_evidence(text: str) -> Evidence:
    """Validate the verification JSON against its closed schema.

    Raises:
        ValueError: A required field is missing or a value is invalid.
        TypeError: A present field has the wrong Python type.
    """
    data = _closed(json.loads(text), _EVIDENCE_FIELDS, "evidence")
    commands: list[Command] = []
    for index, raw in enumerate(_items(data.get("commands"), "commands")):
        item = _closed(raw, _COMMAND_FIELDS, f"commands[{index}]")
        code = item.get("exit_code")
        if "exit_code" not in item:
            raise EvidenceInputError(EvidenceInputIssue.EXIT_CODE, index=index)
        if type(code) is not int:
            raise EvidenceInputTypeError(EvidenceInputIssue.EXIT_CODE, index=index)
        commands.append(
            Command(
                command=_required_text(item, "command", f"commands[{index}].command"),
                exit_code=code,
                summary=_text(item.get("summary"), "summary", required=False),
            )
        )
    acceptance: list[Criterion] = []
    for index, raw in enumerate(_items(data.get("acceptance"), "acceptance")):
        item = _closed(raw, _ACCEPTANCE_FIELDS, f"acceptance[{index}]")
        status = item.get("status")
        if "status" in item and not isinstance(status, str):
            raise EvidenceInputTypeError(
                EvidenceInputIssue.ACCEPTANCE_STATUS, index=index
            )
        if status not in _STATUSES:
            raise EvidenceInputError(EvidenceInputIssue.ACCEPTANCE_STATUS, index=index)
        acceptance.append(
            Criterion(
                criterion=_required_text(
                    item, "criterion", f"acceptance[{index}].criterion"
                ),
                status=str(status),
                evidence=_text(item.get("evidence"), "evidence", required=False),
            )
        )
    lists = {
        name: tuple(
            _text(entry, f"{name}[{index}]")
            for index, entry in enumerate(_items(data.get(name), name))
        )
        for name in ("limitations", "follow_up")
    }
    return Evidence(
        task=_required_text(data, "task", "task"),
        worker=_text(data.get("worker"), "worker", required=False) or "unspecified",
        summary=_text(data.get("summary"), "summary", required=False),
        acceptance=tuple(acceptance),
        commands=tuple(commands),
        limitations=lists["limitations"],
        follow_up=lists["follow_up"],
    )


def _inside(path: str, prefixes: tuple[str, ...]) -> bool:
    """Return True when a POSIX path equals or sits below an allowed prefix."""
    candidate = PurePosixPath(path)
    return any(
        candidate == PurePosixPath(prefix) or PurePosixPath(prefix) in candidate.parents
        for prefix in prefixes
    )


def gate_findings(
    *,
    changes: list[FileChange],
    evidence: Evidence,
    allow: tuple[str, ...],
    diff_name: str,
    evidence_name: str,
) -> list[str]:
    """Return every reason the package is not ready for review."""
    findings: list[str] = []
    if not changes:
        findings.append(f"{diff_name}:1: diff contains no changed files")
    if allow:
        findings.extend(
            f"{diff_name}:{change.line}: '{change.path}' is outside the allowed paths"
            for change in changes
            if not _inside(change.path, allow)
            or (change.old_path is not None and not _inside(change.old_path, allow))
        )
    if not evidence.commands:
        findings.append(f"{evidence_name}:1: no verification command was recorded")
    findings.extend(
        f"{evidence_name}:1: command failed with exit {item.exit_code}: {item.command}"
        for item in evidence.commands
        if item.exit_code != 0
    )
    findings.extend(
        f"{evidence_name}:1: acceptance {item.status}: {item.criterion}"
        for item in evidence.acceptance
        if item.status in {"unmet", "partial"}
    )
    return findings


def _cell(value: str) -> str:
    """Make text safe for a one-line Markdown table cell."""
    return " ".join(value.split()).replace("|", "\\|") or "-"


def _code(value: str) -> str:
    """Render inline code that tolerates backticks in the value."""
    text = " ".join(value.split()).replace("|", "\\|")
    fence = "``" if "`" in text else "`"
    padding = " " if fence == "``" else ""
    return f"{fence}{padding}{text}{padding}{fence}"


def render(
    *,
    changes: list[FileChange],
    evidence: Evidence,
    findings: list[str],
    diff_sha256: str,
) -> str:
    """Render the deterministic Markdown review package."""
    added = sum(item.added for item in changes)
    removed = sum(item.removed for item in changes)
    lines = [
        f"# Review package: {_cell(evidence.task)}",
        "",
        f"- Worker: {_cell(evidence.worker)}",
        f"- Diff SHA-256: `{diff_sha256}`",
        f"- Files: {len(changes)} (+{added} / -{removed})",
        f"- Gate: {'blocked' if findings else 'ready for review'}",
        "",
        "## Summary",
        "",
        evidence.summary or "No summary was provided.",
        "",
        "## Changed files",
        "",
        "| Path | Change | Added | Removed |",
        "| --- | --- | --- | --- |",
    ]
    for item in sorted(changes, key=lambda change: change.path):
        kind = item.status + (" (binary)" if item.binary else "")
        if item.old_path:
            kind += f" from {_code(item.old_path)}"
        lines.append(f"| {_code(item.path)} | {kind} | {item.added} | {item.removed} |")
    lines += ["", "## Verification", ""]
    if evidence.commands:
        lines += ["| Command | Exit | Result |", "| --- | --- | --- |"]
        lines += [
            f"| {_code(item.command)} | {item.exit_code} | {_cell(item.summary)} |"
            for item in evidence.commands
        ]
    else:
        lines.append("No verification command was recorded.")
    lines += ["", "## Acceptance", ""]
    if evidence.acceptance:
        lines += ["| Criterion | Status | Evidence |", "| --- | --- | --- |"]
        lines += [
            f"| {_cell(item.criterion)} | {item.status} | {_cell(item.evidence)} |"
            for item in evidence.acceptance
        ]
    else:
        lines.append("No acceptance criteria were recorded.")
    for title, entries in (
        ("Limitations", evidence.limitations),
        ("Follow-up", evidence.follow_up),
    ):
        lines += ["", f"## {title}", ""]
        lines += [f"- {_cell(entry)}" for entry in entries] or ["- None recorded."]
    lines += ["", "## Gate findings", ""]
    lines += [f"- {_cell(item)}" for item in findings] or ["- None."]
    lines += [
        "",
        "## Reviewer checklist",
        "",
        "- [ ] Every changed path belongs to the assigned scope.",
        "- [ ] Each acceptance criterion has observable evidence.",
        "- [ ] Commands were run after the final edit and match the claims.",
        "- [ ] Negative and boundary cases are covered by tests.",
        "- [ ] No secrets, personal data, or generated copies were edited.",
    ]
    return "\n".join(lines) + "\n"


def _read(path: Path, limit: int) -> str:
    """Read bounded UTF-8 text."""
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise EvidenceInputError(EvidenceInputIssue.FILE_SIZE, path=path, limit=limit)
    return data.decode("utf-8-sig")


def build(
    *,
    diff_path: Path,
    evidence_path: Path,
    allow: tuple[str, ...],
    max_bytes: int,
    stderr: TextIO,
) -> tuple[str | None, int]:
    """Return the rendered package and exit status for the given inputs."""
    try:
        diff_text = _read(diff_path, max_bytes)
        evidence = parse_evidence(_read(evidence_path, max_bytes))
    except (OSError, UnicodeError, ValueError, EvidenceInputTypeError) as error:
        stderr.write(f"review-package: inputs are unusable: {error}\n")
        return None, _CONFIG_EXIT
    changes = parse_diff(diff_text)
    findings = gate_findings(
        changes=changes,
        evidence=evidence,
        allow=tuple(prefix.replace("\\", "/").rstrip("/") for prefix in allow),
        diff_name=str(diff_path),
        evidence_name=str(evidence_path),
    )
    stderr.writelines(f"{item}\n" for item in findings)
    document = render(
        changes=changes,
        evidence=evidence,
        findings=findings,
        diff_sha256=hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
    )
    return document, 1 if findings else 0


_SELF_TEST_DIFF = """diff --git a/src/orders.py b/src/orders.py
index 1111111..2222222 100644
--- a/src/orders.py
+++ b/src/orders.py
@@ -1,2 +1,3 @@
 import json
-x = 1
+x = 2
+y = 3
diff --git a/docs/old.md b/docs/new.md
similarity index 90%
rename from docs/old.md
rename to docs/new.md
diff --git a/tests/test_orders.py b/tests/test_orders.py
new file mode 100644
--- /dev/null
+++ b/tests/test_orders.py
@@ -0,0 +1 @@
+def test_total() -> None: ...
"""


def _self_test() -> int:
    """Run embedded regressions without reading or writing files."""
    changes = {item.path: item for item in parse_diff(_SELF_TEST_DIFF)}
    failures: list[str] = []
    expected = {
        "src/orders.py": ("modified", 2, 1),
        "docs/new.md": ("renamed", 0, 0),
        "tests/test_orders.py": ("added", 1, 0),
    }
    for path, (status, added, removed) in expected.items():
        item = changes.get(path)
        if item is None or (item.status, item.added, item.removed) != (
            status,
            added,
            removed,
        ):
            failures.append(f"diff parse {path}: {item}")
    evidence = parse_evidence(
        json.dumps(
            {
                "task": "orders",
                "commands": [
                    {"command": "pytest", "exit_code": 1, "summary": "1 failed"}
                ],
                "acceptance": [{"criterion": "totals", "status": "unmet"}],
            }
        )
    )
    findings = gate_findings(
        changes=list(changes.values()),
        evidence=evidence,
        allow=("src", "tests"),
        diff_name="d",
        evidence_name="e",
    )
    if len(findings) != 3:  # noqa: PLR2004
        failures.append(f"gate findings {findings}")
    for failure in failures:
        print(f"self-test: {failure}")
    if failures:
        return 1
    print(f"self-test passed: {len(expected) + 1} cases")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Write the review package and return the gate status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--diff", type=Path, help="unified diff file")
    parser.add_argument("--evidence", type=Path, help="verification JSON file")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        help="allowed repository path prefix for changed files; repeatable",
    )
    parser.add_argument("--output", type=Path, help="write Markdown here, not stdout")
    parser.add_argument("--force", action="store_true", help="replace --output")
    parser.add_argument("--max-bytes", type=int, default=_DEFAULT_MAX_BYTES)
    parser.add_argument("--self-test", action="store_true", help="run embedded checks")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    if args.diff is None or args.evidence is None:
        parser.error("--diff and --evidence are required")
    if args.max_bytes < 1:
        parser.error("--max-bytes must be positive")
    if args.output is not None and args.output.exists() and not args.force:
        print(f"{args.output}: exists; pass --force to replace it", file=sys.stderr)
        return _CONFIG_EXIT
    document, status = build(
        diff_path=args.diff,
        evidence_path=args.evidence,
        allow=tuple(args.allow),
        max_bytes=args.max_bytes,
        stderr=sys.stderr,
    )
    if document is None:
        return status
    if args.output is None:
        sys.stdout.write(document)
    else:
        args.output.write_text(document, encoding="utf-8", newline="\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
