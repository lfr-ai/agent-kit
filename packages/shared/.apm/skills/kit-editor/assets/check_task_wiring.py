"""Check that VS Code tasks which call the Task runner name existing Taskfile targets.

The checker reads a workspace 'tasks.json' (JSON with comments and trailing commas,
as VS Code accepts) and a 'Taskfile.yml'. Every task whose 'type' is 'process' or
'shell' and whose command is the 'task' executable must name targets that are
declared under the top-level 'tasks:' mapping of the Taskfile. The Taskfile is
parsed minimally without a YAML library: only top-level task keys are read.

Findings are printed as 'path:line: message' and the exit status is 1 when any
finding exists, 2 when inputs cannot be read, and 0 otherwise.
"""

import argparse
import json
import re
import shlex
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_TASK_EXECUTABLES = frozenset({"task", "task.exe", "go-task", "go-task.exe"})
_RUNNABLE_TYPES = frozenset({"process", "shell"})
_PLATFORM_KEYS = ("windows", "linux", "osx")
_VALUE_FLAGS = frozenset(
    {
        "-d",
        "--dir",
        "-t",
        "--taskfile",
        "-o",
        "--output",
        "--output-group-begin",
        "--output-group-end",
        "-C",
        "--concurrency",
        "-I",
        "--interval",
    }
)
_LISTING_FLAGS = frozenset(
    {"-l", "--list", "-a", "--list-all", "--version", "-h", "--help", "-i", "--init"}
)
_TOP_LEVEL_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s|$)")
_NESTED_KEY = re.compile(
    r"""^(?P<indent>[ ]+)(?:"(?P<dq>[^"]+)"|'(?P<sq>[^']+)'|(?P<bare>[^\s#'"][^#]*?)):(?:\s|$)"""
)
_VARIABLE = re.compile(r"\$\{[^}]+\}")
_CLOSING = re.compile(r"\s*[}\]]")


@dataclass(frozen=True, kw_only=True, slots=True)
class Taskfile:
    """Top-level names declared by a Taskfile.

    Attributes:
        tasks: Names declared directly under the top-level 'tasks:' key.
        includes: Namespaces declared under the top-level 'includes:' key.
    """

    tasks: frozenset[str]
    includes: frozenset[str]


@dataclass(frozen=True, kw_only=True, slots=True)
class Invocation:
    """One editor task that invokes the Task runner.

    Attributes:
        label: The editor task label, or a positional placeholder.
        line: The 1-based line in 'tasks.json' where the task label appears.
        targets: Task names passed to the runner, in order.
        dynamic: Arguments containing unresolved editor variables.
        listing: Whether a flag such as '--list' makes a target unnecessary.
    """

    label: str
    line: int
    targets: tuple[str, ...]
    dynamic: tuple[str, ...]
    listing: bool


def strip_jsonc(text: str) -> str:
    """Remove comments and trailing commas while preserving line numbers.

    Args:
        text: JSON text that may contain line comments, block comments and
            trailing commas before a closing bracket or brace.

    Returns:
        Strict JSON text with the same number of lines as the input.
    """
    output: list[str] = []
    index = 0
    in_string = False
    length = len(text)
    while index < length:
        char = text[index]
        if in_string:
            output.append(char)
            if char == "\\" and index + 1 < length:
                output.append(text[index + 1])
                index += 2
                continue
            if char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if text.startswith("//", index):
            end = text.find("\n", index)
            index = length if end == -1 else end
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            stop = length if end == -1 else end + 2
            output.append("\n" * text.count("\n", index, stop))
            index = stop
            continue
        output.append(char)
        index += 1
    return _drop_trailing_commas("".join(output))


def _drop_trailing_commas(text: str) -> str:
    """Remove commas that directly precede a closing bracket outside strings."""
    output: list[str] = []
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "," and _CLOSING.match(text, index + 1):
            continue
        output.append(char)
    return "".join(output)


def parse_taskfile(text: str) -> Taskfile:
    """Read top-level task and include names from Taskfile YAML text.

    Only block mappings are understood. Keys may be bare, single-quoted or
    double-quoted, and may contain colons such as 'docs:build'.

    Args:
        text: The Taskfile content.

    Returns:
        The declared task names and include namespaces.
    """
    sections: dict[str, set[str]] = {"tasks": set(), "includes": set()}
    current: str | None = None
    child_indent: int | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        if indent == 0:
            match = _TOP_LEVEL_KEY.match(line)
            current = match.group(1) if match and match.group(1) in sections else None
            child_indent = None
            continue
        if current is None:
            continue
        if child_indent is None:
            child_indent = indent
        if indent != child_indent:
            continue
        nested = _NESTED_KEY.match(line)
        if nested:
            name = nested.group("dq") or nested.group("sq") or nested.group("bare")
            sections[current].add(name.strip())
    return Taskfile(
        tasks=frozenset(sections["tasks"]), includes=frozenset(sections["includes"])
    )


def _command_words(definition: dict[str, object]) -> list[str] | None:
    """Return the executable and arguments of one task definition."""
    command = definition.get("command")
    if not isinstance(command, str):
        return None
    raw_args = definition.get("args", [])
    args = (
        [item for item in raw_args if isinstance(item, str)]
        if isinstance(raw_args, list)
        else []
    )
    words = [command, *args]
    if definition.get("type") == "shell" and " " in command.strip():
        try:
            words = [*shlex.split(command), *args]
        except ValueError:
            return None
    return words


def targets_from_words(words: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Separate Task runner targets from flags, variables and pass-through args.

    Args:
        words: The executable followed by its arguments.

    Returns:
        A pair of resolved target names and arguments containing editor
        variables that cannot be checked statically.
    """
    targets: list[str] = []
    dynamic: list[str] = []
    skip_value = False
    for word in words[1:]:
        if skip_value:
            skip_value = False
            continue
        if word == "--":
            break
        if word.startswith("-"):
            skip_value = word in _VALUE_FLAGS
            continue
        if "=" in word:
            continue
        if _VARIABLE.search(word):
            dynamic.append(word)
            continue
        targets.append(word)
    return tuple(targets), tuple(dynamic)


def _label_line(text: str, label: str) -> int:
    """Locate the line declaring a label, falling back to the first line."""
    needle = json.dumps(label)
    for number, line in enumerate(text.splitlines(), start=1):
        if needle in line and '"label"' in line:
            return number
    return 1


class TaskInputIssue(StrEnum):
    """Supported task input validation failures and their stable messages."""

    DOCUMENT_SHAPE = "tasks.json must be an object with a 'tasks' list"


class TaskInputError(ValueError):
    """An input violates the task input contract."""

    def __init__(self, issue: TaskInputIssue) -> None:
        """Describe a supported input failure.

        Args:
            issue: The violated input invariant.
        """
        super().__init__(issue.value)


class TaskInputTypeError(TypeError):
    """An input has the wrong Python type for the task input contract."""

    def __init__(self, issue: TaskInputIssue) -> None:
        """Describe a wrong input type.

        Args:
            issue: The violated input invariant.
        """
        super().__init__(issue.value)


def invocations(text: str) -> list[Invocation]:
    """Find editor tasks, including platform overrides, that call the Task runner.

    Args:
        text: The 'tasks.json' content, with or without comments.

    Returns:
        Each Task runner invocation with its targets and source line.

    Raises:
        ValueError: The content is not a JSON object with a 'tasks' list.
        TypeError: A present JSON container has the wrong Python type.
    """
    document = json.loads(strip_jsonc(text))
    if not isinstance(document, dict):
        raise TaskInputTypeError(TaskInputIssue.DOCUMENT_SHAPE)
    if "tasks" not in document:
        raise TaskInputError(TaskInputIssue.DOCUMENT_SHAPE)
    if not isinstance(document["tasks"], list):
        raise TaskInputTypeError(TaskInputIssue.DOCUMENT_SHAPE)
    found: list[Invocation] = []
    for position, task in enumerate(document["tasks"], start=1):
        if not isinstance(task, dict):
            continue
        label = task.get("label")
        label = label if isinstance(label, str) else f"task #{position}"
        line = _label_line(text, label)
        variants = [task]
        for key in _PLATFORM_KEYS:
            override = task.get(key)
            if isinstance(override, dict):
                variants.append({**task, **override})
        for variant in variants:
            if variant.get("type", "process") not in _RUNNABLE_TYPES:
                continue
            words = _command_words(variant)
            if not words or Path(words[0]).name.casefold() not in _TASK_EXECUTABLES:
                continue
            targets, dynamic = targets_from_words(words)
            found.append(
                Invocation(
                    label=label,
                    line=line,
                    targets=targets,
                    dynamic=dynamic,
                    listing=any(word in _LISTING_FLAGS for word in words[1:]),
                )
            )
    return found


def check(
    tasks_text: str,
    taskfile: Taskfile,
    *,
    tasks_path: str,
    allow_dynamic: bool = False,
    verify_includes: bool = False,
) -> list[str]:
    """Report editor tasks whose Task runner targets are not declared.

    Args:
        tasks_text: The 'tasks.json' content.
        taskfile: Names parsed from the Taskfile.
        tasks_path: Display path used in findings.
        allow_dynamic: Accept arguments built from editor variables.
        verify_includes: Reject targets in included namespaces, which cannot
            be verified without reading the included Taskfile files.

    Returns:
        Sorted 'path:line: message' findings.
    """
    findings: set[str] = set()
    for item in invocations(tasks_text):
        if not allow_dynamic:
            findings.update(
                f"{tasks_path}:{item.line}: task '{item.label}' passes "
                f"unverifiable argument '{word}'"
                for word in item.dynamic
            )
        implicit = () if item.dynamic or item.listing else ("default",)
        names = item.targets or implicit
        for name in names:
            if name in taskfile.tasks:
                continue
            namespace = name.split(":", 1)[0]
            if ":" in name and namespace in taskfile.includes and not verify_includes:
                continue
            findings.add(
                f"{tasks_path}:{item.line}: task '{item.label}' targets "
                f"'{name}', which the Taskfile does not declare"
            )
    return sorted(findings, key=_finding_order)


def _finding_order(finding: str) -> tuple[int, str]:
    """Sort findings by line number, then text."""
    parts = finding.rsplit(": task ", 1)[0].rsplit(":", 1)
    line = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return line, finding


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    TASKFILE_PARSE = "unexpected Taskfile parse: {taskfile}"
    DECLARED_TARGET_REJECTED = "declared targets must pass"
    UNEXPECTED_FINDINGS = "unexpected findings: {findings}"
    DYNAMIC_ARGUMENT_REJECTED = "allowed dynamic arguments must pass"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(
        self,
        issue: SelfTestIssue,
        *,
        taskfile: Taskfile | None = None,
        findings: list[str] | None = None,
    ) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
            taskfile: Observed taskfile for the failing case.
            findings: Observed findings for the failing case.
        """
        super().__init__(issue.value.format(taskfile=taskfile, findings=findings))


def self_test() -> None:
    """Exercise parsing and checking with in-memory synthetic inputs.

    Raises:
        AssertionError: A synthetic case produced an unexpected result.
    """
    taskfile = parse_taskfile(
        'version: "3"\n'
        "includes:\n  docs: ./docs/Taskfile.yml\n"
        "tasks:\n"
        "  default:\n    cmds: [task --list]\n"
        "  verify:\n    desc: Gate\n    cmds:\n      - echo ok\n"
        "  'lint:fix':\n    cmds: [echo fix]\n"
        "  format:check: echo check\n"
        "vars:\n  NAME: value\n"
    )
    expected = frozenset({"default", "verify", "lint:fix", "format:check"})
    if taskfile.tasks != expected or taskfile.includes != frozenset({"docs"}):
        raise SelfTestError(SelfTestIssue.TASKFILE_PARSE, taskfile=taskfile)
    good = (
        '{\n  // comment\n  "version": "2.0.0",\n  "tasks": [\n'
        '    {"label": "Verify", "type": "process", "command": "task",'
        ' "args": ["verify"],},\n'
        '    {"label": "Docs", "type": "shell", "command": "task docs:build"},\n'
        '    {"label": "Default", "type": "process", "command": "task"},\n'
        '    {"label": "List", "type": "process", "command": "task", "args": ["-l"]},\n'
        '    {"label": "Other", "type": "npm", "script": "build"}\n  ]\n}\n'
    )
    if check(good, taskfile, tasks_path="tasks.json"):
        raise SelfTestError(SelfTestIssue.DECLARED_TARGET_REJECTED)
    bad = (
        '{"tasks": [\n{"label": "Missing", "command": "task", "args": ["-d", "x",'
        ' "deploy"]},\n{"label": "Input", "command": "task",'
        ' "args": ["${input:name}"]}\n]}\n'
    )
    findings = check(bad, taskfile, tasks_path="tasks.json")
    if len(findings) != 2 or not findings[0].startswith("tasks.json:2:"):  # noqa: PLR2004
        raise SelfTestError(SelfTestIssue.UNEXPECTED_FINDINGS, findings=findings)
    if check(
        bad.replace("deploy", "verify"), taskfile, tasks_path="t", allow_dynamic=True
    ):
        raise SelfTestError(SelfTestIssue.DYNAMIC_ARGUMENT_REJECTED)


def main(argv: list[str] | None = None) -> int:
    """Check task wiring for one workspace.

    Args:
        argv: Command-line arguments; defaults to 'sys.argv'.

    Returns:
        0 when every target is declared, 1 on findings, 2 on unreadable input.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tasks", type=Path, default=Path(".vscode/tasks.json"))
    parser.add_argument("--taskfile", type=Path, default=Path("Taskfile.yml"))
    parser.add_argument(
        "--allow-dynamic",
        action="store_true",
        help="accept arguments containing editor variables such as '${input:x}'",
    )
    parser.add_argument(
        "--verify-includes",
        action="store_true",
        help="fail targets in included namespaces instead of accepting them",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("Task wiring checker self-test passed.")
        return 0
    try:
        tasks_text = args.tasks.read_text(encoding="utf-8")
        taskfile = parse_taskfile(args.taskfile.read_text(encoding="utf-8"))
        findings = check(
            tasks_text,
            taskfile,
            tasks_path=args.tasks.as_posix(),
            allow_dynamic=args.allow_dynamic,
            verify_includes=args.verify_includes,
        )
    except (OSError, UnicodeError, ValueError, TaskInputTypeError) as error:
        print(f"Cannot check task wiring: {error}", file=sys.stderr)
        return 2
    for finding in findings:
        print(finding)
    if not findings:
        print(f"All Task runner targets in {args.tasks.as_posix()} are declared.")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
