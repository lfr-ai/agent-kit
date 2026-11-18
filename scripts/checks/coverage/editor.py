"""Editor tasks as thin wrappers over canonical Taskfile targets."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from agent_kit.core.guards import is_json_object, is_str_list
from scripts.checks.coverage.inputs import read_json

if TYPE_CHECKING:
    from pathlib import Path


def _editor_task_entry_failures(
    task: object, definitions: dict[str, object]
) -> list[str]:
    """Require one editor task to be a thin wrapper over a Taskfile target.

    Args:
        task (object): Decoded editor task entry.
        definitions (dict[str, object]): Taskfile target definitions by name.

    Returns:
        list[str]: One failure per violated wrapper rule; empty for a valid wrapper.
    """
    if (
        not is_json_object(task)
        or task.get("type") != "process"
        or task.get("command") != "task"
    ):
        return ["editor task is not a thin canonical Task wrapper"]
    failures: list[str] = []
    args = task.get("args")
    if not is_str_list(args) or len(args) != 1 or args[0] not in definitions:
        failures.append("editor task references an unavailable Taskfile target")
    if task.get("options") != {"cwd": "${workspaceFolder}"}:
        failures.append("editor task must target the active workspace directory")
    return failures


def editor_task_failures(root: Path) -> list[str]:
    """Require editor tasks to delegate to canonical Taskfile targets."""
    tasks: object = read_json(root / ".vscode/tasks.json")
    taskfile = yaml.safe_load((root / "Taskfile.yml").read_text(encoding="utf-8"))
    if not is_json_object(tasks) or not is_json_object(taskfile):
        return ["editor/task definitions cannot be parsed"]
    definitions = taskfile.get("tasks", {})
    if not is_json_object(definitions):
        definitions = {}
    task_entries = tasks.get("tasks", [])
    failures: list[str] = []
    if not isinstance(task_entries, list):
        failures.append("editor/task definitions cannot be parsed")
        task_entries = []
    for task in task_entries:
        failures.extend(_editor_task_entry_failures(task, definitions))
    return failures
