"""Review Azure what-if changes or properties.changes envelopes without deployment.

Use --file or --self-test. Exit 2 rejects malformed/unsupported input, 3 flags
deletes, and 4 flags recreate or unresolved/ignored changes. No approval overrides,
authentication, network access or resource mutations are supported.
"""

import argparse
from collections.abc import Callable
from enum import StrEnum
import json
from pathlib import Path
import sys

_INVALID = 2
_DELETE = 3
_REVIEW = 4
_KINDS = {
    "Create": "create",
    "Modify": "modify",
    "NoChange": "no-change",
    "Delete": "delete",
    "Recreate": "recreate",
    "Deploy": "review",
    "Ignore": "review",
    "Unsupported": "review",
}


class WhatIfInputIssue(StrEnum):
    """Supported what-if input validation failures and their stable messages."""

    DUPLICATE_PROPERTY = "duplicate JSON property"
    NON_JSON_CONSTANT = "non-JSON constant: {value}"
    OBJECT_REQUIRED = "what-if result must be an object"
    UNFINISHED_RESULT = "failed or unfinished what-if result cannot be reviewed"
    AMBIGUOUS_ENVELOPE = "ambiguous changes envelopes"
    MISSING_CHANGES = "expected changes or properties.changes"
    CHANGES_ARRAY = "changes must be an explicit array"
    CHANGE_OBJECT = "each change must be an object"
    RESOURCE_ID = "each change needs a nonempty unique resourceId"
    CHANGE_TYPE = "unsupported or missing changeType"


class WhatIfInputError(ValueError):
    """An input violates the what-if input contract."""

    def __init__(self, issue: WhatIfInputIssue, *, value: str | None = None) -> None:
        """Describe a supported input failure.

        Args:
            issue: The violated input invariant.
            value: Diagnostic value for the invalid input.
        """
        super().__init__(issue.value.format(value=value))


class WhatIfInputTypeError(TypeError):
    """An input has the wrong Python type for the what-if input contract."""

    def __init__(self, issue: WhatIfInputIssue) -> None:
        """Describe a wrong input type.

        Args:
            issue: The violated input invariant.
        """
        super().__init__(issue.value)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WhatIfInputError(WhatIfInputIssue.DUPLICATE_PROPERTY)
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise WhatIfInputError(WhatIfInputIssue.NON_JSON_CONSTANT, value=value)


def _check_status(value: dict[object, object]) -> None:
    if "status" in value and not isinstance(value["status"], str):
        raise WhatIfInputTypeError(WhatIfInputIssue.UNFINISHED_RESULT)
    if (
        value.get("error") is not None
        or value.get("status", "Succeeded") != "Succeeded"
    ):
        raise WhatIfInputError(WhatIfInputIssue.UNFINISHED_RESULT)


def _select_changes(value: dict[object, object]) -> object:
    properties = value.get("properties")
    nested = isinstance(properties, dict) and "changes" in properties
    if "changes" in value and nested:
        raise WhatIfInputError(WhatIfInputIssue.AMBIGUOUS_ENVELOPE)
    if "changes" in value:
        return value["changes"]
    if isinstance(properties, dict) and nested:
        return properties["changes"]
    raise WhatIfInputError(WhatIfInputIssue.MISSING_CHANGES)


def _changes(value: object) -> list[object]:
    if not isinstance(value, dict):
        raise WhatIfInputTypeError(WhatIfInputIssue.OBJECT_REQUIRED)
    _check_status(value)
    changes = _select_changes(value)
    if not isinstance(changes, list):
        raise WhatIfInputTypeError(WhatIfInputIssue.CHANGES_ARRAY)
    return changes


def _resource_id(change: dict[object, object], seen: set[str]) -> str:
    resource = change.get("resourceId")
    if "resourceId" not in change:
        raise WhatIfInputError(WhatIfInputIssue.RESOURCE_ID)
    if not isinstance(resource, str):
        raise WhatIfInputTypeError(WhatIfInputIssue.RESOURCE_ID)
    if not resource.strip() or resource.casefold() in seen:
        raise WhatIfInputError(WhatIfInputIssue.RESOURCE_ID)
    seen.add(resource.casefold())
    return resource


def _change_kind(change: dict[object, object]) -> str:
    action = change.get("changeType")
    if "changeType" not in change:
        raise WhatIfInputError(WhatIfInputIssue.CHANGE_TYPE)
    if not isinstance(action, str):
        raise WhatIfInputTypeError(WhatIfInputIssue.CHANGE_TYPE)
    if action not in _KINDS:
        raise WhatIfInputError(WhatIfInputIssue.CHANGE_TYPE)
    return _KINDS[action]


def analyze_whatif(value: object) -> dict[str, list[str]]:
    """Classify explicit resource changes; never guess missing IDs or actions.

    Raises:
        ValueError: A required field is missing or a change value is unsupported.
        TypeError: The document or a present field has the wrong Python type.
    """
    groups: dict[str, list[str]] = {kind: [] for kind in _KINDS.values()}
    seen: set[str] = set()
    for change in _changes(value):
        if not isinstance(change, dict):
            raise WhatIfInputTypeError(WhatIfInputIssue.CHANGE_OBJECT)
        resource = _resource_id(change, seen)
        groups[_change_kind(change)].append(resource)
    return groups


def _read(text: str) -> dict[str, list[str]]:
    return analyze_whatif(
        json.loads(
            text, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant
        )
    )


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    CLASSIFICATION = "what-if classification regressed"
    INVALID_RESULT_ACCEPTED = "unsupported what-if result was accepted"
    INVALID_JSON_ACCEPTED = "malformed JSON was accepted"
    EMPTY_PREVIEW = "explicit empty preview must have zero changes"


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
    """Exercise supported, risky, malformed and incomplete preview inputs."""
    for action, kind in _KINDS.items():
        groups = analyze_whatif(
            {"changes": [{"resourceId": "/example", "changeType": action}]}
        )
        if groups[kind] != ["/example"]:
            raise SelfTestError(SelfTestIssue.CLASSIFICATION)
    invalid: tuple[object, ...] = (
        {},
        {"status": "Failed", "changes": []},
        {"unrelated": {"changes": []}},
        {"changes": [{}]},
        {"changes": [{"resourceId": "/example", "changeType": "Unknown"}]},
        {"changes": [], "properties": {"changes": []}},
    )
    _expect_rejected(
        invalid, analyze_whatif, ValueError, SelfTestIssue.INVALID_RESULT_ACCEPTED
    )
    _expect_rejected(
        ([], {"changes": None}),
        analyze_whatif,
        WhatIfInputTypeError,
        SelfTestIssue.INVALID_RESULT_ACCEPTED,
    )
    _expect_rejected(
        ("{", '{"changes":[],"changes":[]}', "NaN"),
        _read_object,
        ValueError,
        SelfTestIssue.INVALID_JSON_ACCEPTED,
    )
    if any(analyze_whatif({"properties": {"changes": []}}).values()):
        raise SelfTestError(SelfTestIssue.EMPTY_PREVIEW)


def main() -> int:
    """Emit valid summaries and fail explicitly for risks or unsupported input."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", "-f", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("Azure what-if reviewer self-test passed.")
        return 0
    if args.file is None:
        parser.error("--file is required unless --self-test is selected")
    try:
        groups = _read(args.file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, WhatIfInputTypeError) as error:
        print(f"Cannot review what-if: {error}", file=sys.stderr)
        return _INVALID
    print(
        json.dumps(
            {
                "summary": {key: len(items) for key, items in groups.items()},
                "lists": groups,
            }
        )
    )
    if groups["delete"] or groups["recreate"] or groups["review"]:
        print(
            "Destructive or unresolved changes require operator review; no deployment is authorized.",
            file=sys.stderr,
        )
        return _DELETE if groups["delete"] else _REVIEW
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
