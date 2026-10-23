"""Summarize explicit Terraform JSON format 1.x plans without authorizing apply.

Use --file for terraform show -json output or --self-test for isolated regressions.
Exit 2 rejects malformed/unsupported input, 3 flags deletes, and 4 flags replacements.
No credentials, network access, state changes or approval overrides are supported.
"""

import argparse
from collections.abc import Callable
from enum import StrEnum
import json
from pathlib import Path
import re
import sys

_INVALID = 2
_DELETE = 3
_REPLACE = 4
_ACTIONS = {
    ("no-op",): "no-op",
    ("read",): "read",
    ("create",): "create",
    ("update",): "update",
    ("delete",): "delete",
    ("delete", "create"): "replace",
    ("create", "delete"): "replace",
}


class PlanInputIssue(StrEnum):
    """Supported plan input validation failures and their stable messages."""

    DUPLICATE_PROPERTY = "duplicate JSON property"
    NON_JSON_CONSTANT = "non-JSON constant: {value}"
    OBJECT_REQUIRED = "plan must be an object"
    FORMAT_VERSION = "supported Terraform format_version is 1.x"
    INCOMPLETE_PLAN = "errored or incomplete plan cannot be reviewed"
    DEFERRED_CHANGES = "deferred changes require manual review"
    CHANGES_ARRAY = "resource_changes must be an explicit array"
    CHANGE_OBJECT = "each resource change must be an object"
    RESOURCE_ADDRESS = "each resource needs a nonempty unique address"
    CHANGE_DETAIL = "each resource needs a change object"
    ACTIONS_ARRAY = "change.actions must be a supported string array"
    UNSUPPORTED_ACTIONS = "unsupported change.actions require manual review"


class PlanInputError(ValueError):
    """An input violates the plan input contract."""

    def __init__(self, issue: PlanInputIssue, *, value: str | None = None) -> None:
        """Describe a supported input failure.

        Args:
            issue: The violated input invariant.
            value: Diagnostic value for the invalid input.
        """
        super().__init__(issue.value.format(value=value))


class PlanInputTypeError(TypeError):
    """An input has the wrong Python type for the plan input contract."""

    def __init__(self, issue: PlanInputIssue) -> None:
        """Describe a wrong input type.

        Args:
            issue: The violated input invariant.
        """
        super().__init__(issue.value)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PlanInputError(PlanInputIssue.DUPLICATE_PROPERTY)
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise PlanInputError(PlanInputIssue.NON_JSON_CONSTANT, value=value)


def _check_version(value: dict[object, object]) -> None:
    version = value.get("format_version")
    if "format_version" not in value:
        raise PlanInputError(PlanInputIssue.FORMAT_VERSION)
    if not isinstance(version, str):
        raise PlanInputTypeError(PlanInputIssue.FORMAT_VERSION)
    if re.fullmatch(r"1\.\d+", version) is None:
        raise PlanInputError(PlanInputIssue.FORMAT_VERSION)


def _check_complete(value: dict[object, object]) -> None:
    if not isinstance(value.get("errored", False), bool) or not isinstance(
        value.get("complete", True), bool
    ):
        raise PlanInputTypeError(PlanInputIssue.INCOMPLETE_PLAN)
    if (
        value.get("errored", False) is not False
        or value.get("complete", True) is not True
    ):
        raise PlanInputError(PlanInputIssue.INCOMPLETE_PLAN)
    deferred = value.get("deferred_changes", [])
    if not isinstance(deferred, list):
        raise PlanInputTypeError(PlanInputIssue.DEFERRED_CHANGES)
    if deferred:
        raise PlanInputError(PlanInputIssue.DEFERRED_CHANGES)


def _resource_changes(value: dict[object, object]) -> list[object]:
    changes = value.get("resource_changes")
    if "resource_changes" not in value:
        raise PlanInputError(PlanInputIssue.CHANGES_ARRAY)
    if not isinstance(changes, list):
        raise PlanInputTypeError(PlanInputIssue.CHANGES_ARRAY)
    return changes


def _address(change: dict[object, object], seen: set[str]) -> str:
    address = change.get("address")
    if "address" not in change:
        raise PlanInputError(PlanInputIssue.RESOURCE_ADDRESS)
    if not isinstance(address, str):
        raise PlanInputTypeError(PlanInputIssue.RESOURCE_ADDRESS)
    if not address.strip() or address in seen:
        raise PlanInputError(PlanInputIssue.RESOURCE_ADDRESS)
    seen.add(address)
    return address


def _action_kind(change: dict[object, object]) -> str:
    detail = change.get("change")
    if "change" not in change:
        raise PlanInputError(PlanInputIssue.CHANGE_DETAIL)
    if not isinstance(detail, dict):
        raise PlanInputTypeError(PlanInputIssue.CHANGE_DETAIL)
    actions = detail.get("actions")
    if "actions" not in detail:
        raise PlanInputError(PlanInputIssue.ACTIONS_ARRAY)
    if not isinstance(actions, list) or not all(
        isinstance(action, str) for action in actions
    ):
        raise PlanInputTypeError(PlanInputIssue.ACTIONS_ARRAY)
    kind = _ACTIONS.get(tuple(actions))
    if kind is None:
        raise PlanInputError(PlanInputIssue.UNSUPPORTED_ACTIONS)
    return kind


def analyze_plan(value: object) -> dict[str, list[str]]:
    """Reject incomplete/unknown input and classify supported resource actions.

    Raises:
        ValueError: A required field is missing or a plan value is unsupported.
        TypeError: The document or a present field has the wrong Python type.
    """
    if not isinstance(value, dict):
        raise PlanInputTypeError(PlanInputIssue.OBJECT_REQUIRED)
    _check_version(value)
    _check_complete(value)
    changes = _resource_changes(value)
    groups: dict[str, list[str]] = {kind: [] for kind in _ACTIONS.values()}
    seen: set[str] = set()
    for change in changes:
        if not isinstance(change, dict):
            raise PlanInputTypeError(PlanInputIssue.CHANGE_OBJECT)
        address = _address(change, seen)
        groups[_action_kind(change)].append(address)
    return groups


def _read(text: str) -> dict[str, list[str]]:
    return analyze_plan(
        json.loads(
            text, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant
        )
    )


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    CLASSIFICATION = "resource action classification regressed"
    INVALID_PLAN_ACCEPTED = "unsupported plan was accepted"
    INVALID_JSON_ACCEPTED = "malformed JSON was accepted"
    EMPTY_PLAN = "explicit empty plan must have zero changes"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(self, issue: SelfTestIssue) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
        """
        super().__init__(issue.value)


def _expect_rejected(
    values: tuple[object, ...],
    check: Callable[[object], object],
    errors: type[Exception] | tuple[type[Exception], ...],
    issue: SelfTestIssue,
) -> None:
    for value in values:
        try:
            check(value)
        except errors:
            continue
        raise SelfTestError(issue)


def _read_object(value: object) -> object:
    if not isinstance(value, str):
        raise TypeError
    return _read(value)


def self_test() -> None:
    """Exercise ordinary, risky, unsupported, incomplete and duplicate inputs."""
    for actions, kind in _ACTIONS.items():
        groups = analyze_plan(
            {
                "format_version": "1.2",
                "resource_changes": [
                    {"address": "example.item", "change": {"actions": list(actions)}}
                ],
            }
        )
        if groups[kind] != ["example.item"]:
            raise SelfTestError(SelfTestIssue.CLASSIFICATION)
    invalid: tuple[object, ...] = (
        {},
        {"format_version": "99.0", "resource_changes": []},
        {"format_version": "1.2", "resource_changes": [], "complete": False},
        {"format_version": "1.2", "resource_changes": [{}]},
        {
            "format_version": "1.2",
            "resource_changes": [
                {"address": "item", "change": {"actions": ["unknown"]}}
            ],
        },
    )
    _expect_rejected(
        invalid, analyze_plan, ValueError, SelfTestIssue.INVALID_PLAN_ACCEPTED
    )
    _expect_rejected(
        ([], {"format_version": "1.2", "resource_changes": None}),
        analyze_plan,
        PlanInputTypeError,
        SelfTestIssue.INVALID_PLAN_ACCEPTED,
    )
    _expect_rejected(
        ("{", '{"format_version":"1.2","format_version":"1.3"}', "NaN"),
        _read_object,
        ValueError,
        SelfTestIssue.INVALID_JSON_ACCEPTED,
    )
    if any(analyze_plan({"format_version": "1.2", "resource_changes": []}).values()):
        raise SelfTestError(SelfTestIssue.EMPTY_PLAN)


def main() -> int:
    """Emit a summary for valid input; risky changes retain a nonzero exit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", "-f", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("Terraform reviewer self-test passed.")
        return 0
    if args.file is None:
        parser.error("--file is required unless --self-test is selected")
    try:
        groups = _read(args.file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, PlanInputTypeError) as error:
        print(f"Cannot review plan: {error}", file=sys.stderr)
        return _INVALID
    print(
        json.dumps(
            {
                "summary": {key: len(items) for key, items in groups.items()},
                "lists": groups,
            }
        )
    )
    if groups["delete"] or groups["replace"]:
        print(
            "Destructive changes require operator review; no apply is authorized.",
            file=sys.stderr,
        )
        return _DELETE if groups["delete"] else _REPLACE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
