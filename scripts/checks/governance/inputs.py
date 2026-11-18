"""Decoded governance inputs, their stable diagnostics, and safe accessors."""

from __future__ import annotations

from enum import Enum, unique
from typing import TYPE_CHECKING, override

import yaml

from agent_kit.core.guards import is_json_object

if TYPE_CHECKING:
    from pathlib import Path

    from yaml.nodes import MappingNode


@unique
class GovernanceIssue(Enum):
    """Stable diagnostics for malformed governance input."""

    DUPLICATE_WORKFLOW_KEY = "workflow contains a duplicate or non-string key"
    DUPLICATE_MAINTAINER_FIELD = "maintainer configuration contains duplicate fields"
    INVALID_MAINTAINER_FIELDS = "maintainer configuration has missing or unknown fields"
    INVALID_MAINTAINER_SCHEMA = "maintainer schema_version must be 1"
    INVALID_OWNERS = "owners must be unique GitHub account or team handles"
    INVALID_REPOSITORY = "repository must be an approved owner/name coordinate"
    INVALID_CONTACT = "must be a private HTTPS or mailto contact route"


class GovernanceInputError(ValueError):
    """Report one known governance input contract failure."""

    def __init__(self, issue: GovernanceIssue, *, field: str | None = None) -> None:
        """Prefix a contact ``issue`` with optional ``field``; retain both."""
        self.issue = issue
        self.field = field
        message = (
            f"{field} {issue.value}"
            if issue is GovernanceIssue.INVALID_CONTACT and field is not None
            else issue.value
        )
        super().__init__(message)


class _WorkflowLoader(yaml.BaseLoader):
    """Parse workflow scalars as strings and reject duplicate mapping keys."""

    @override
    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[str, object]:
        """Prevent duplicate keys from overriding earlier permission declarations.

        Raises:
            GovernanceInputError: A workflow key is repeated.
        """
        result: dict[str, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise GovernanceInputError(GovernanceIssue.DUPLICATE_WORKFLOW_KEY)
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def load_workflow(path: Path) -> object:
    """Parse one workflow with string scalars and unique mapping keys."""
    loader = _WorkflowLoader(path.read_text(encoding="utf-8"))
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def yaml_mapping(path: Path) -> dict[str, object] | None:
    """Return one decoded YAML mapping, or ``None`` when unreadable or not a mapping."""
    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return raw if is_json_object(raw) else None


def child_value(value: object, key: str) -> object:
    """Return a decoded object's field.

    Args:
        value (object): Decoded value that may be an object.
        key (str): Field name to read.

    Returns:
        object: ``value[key]``, or ``None`` when ``value`` is not an object or lacks the key.
    """
    return value.get(key) if is_json_object(value) else None


def child_list(value: object, key: str) -> list[object]:
    """Return a decoded object's list field.

    Args:
        value (object): Decoded value that may be an object.
        key (str): Field name to read.

    Returns:
        list[object]: ``value[key]`` when it is a list, otherwise an empty list.
    """
    child = child_value(value, key)
    return child if isinstance(child, list) else []


def job_needs(job: object) -> list[object] | None:
    """Return a job's ``needs`` as a list, accepting the one-string shorthand."""
    needs = child_value(job, "needs")
    if isinstance(needs, str):
        return [needs]
    return needs if isinstance(needs, list) else None


def run_commands(job: object) -> list[str]:
    """Return a job's literal shell commands in step order."""
    return [
        command
        for step in child_list(job, "steps")
        if is_json_object(step) and isinstance(command := step.get("run"), str)
    ]
