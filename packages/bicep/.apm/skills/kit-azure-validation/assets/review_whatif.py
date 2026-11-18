# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Review Azure what-if changes or properties.changes envelopes without deployment.

Use --file or --self-test. Exit 2 rejects malformed/unsupported input, 3 flags
deletes, and 4 flags recreate or unresolved/ignored changes. No approval overrides,
authentication, network access or resource mutations are supported.
"""

import argparse
from collections.abc import Callable
from enum import StrEnum, unique
import json
from pathlib import Path
import sys

_INVALID = 2
_DELETE = 3
_REVIEW = 4
_SUCCEEDED = "Succeeded"
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


@unique
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
            issue (WhatIfInputIssue): The violated input invariant.
            value (str | None): Rejected JSON constant, such as ``NaN``, substituted
                into the message.
        """
        super().__init__(issue.value.format(value=value))


class WhatIfInputTypeError(TypeError):
    """An input has the wrong Python type for the what-if input contract."""

    def __init__(self, issue: WhatIfInputIssue) -> None:
        """Describe a wrong input type.

        Args:
            issue (WhatIfInputIssue): The violated input invariant.
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
    if value.get("error") is not None or value.get("status", _SUCCEEDED) != _SUCCEEDED:
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
    """Return resource IDs keyed by change kind; never guess missing IDs or actions.

    Kinds are ``create``, ``modify``, ``no-change``, ``delete``, ``recreate`` and
    ``review``; every kind is present, empty when unused, and IDs keep document order.
    Raises ``WhatIfInputTypeError`` when the document or a present field has the wrong
    type; a missing field or unsupported value propagates from the field helpers as
    ``WhatIfInputError`` (a ``ValueError``).
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


def _accepts_any(
    values: tuple[object, ...],
    check: Callable[[object], object],
    errors: type[Exception] | tuple[type[Exception], ...],
) -> bool:
    """Return whether ``check`` completes for any value without raising ``errors``."""
    for value in values:
        try:
            check(value)
        except errors:
            continue
        return True
    return False


def _read_object(value: object) -> object:
    if not isinstance(value, str):
        raise TypeError
    return _read(value)


def _classifies(action: str, kind: str) -> bool:
    """Return whether a one-change preview of ``action`` is grouped under ``kind``."""
    groups = analyze_whatif(
        {"changes": [{"resourceId": "/example", "changeType": action}]}
    )
    return groups[kind] == ["/example"]


def self_test() -> list[str]:
    """Exercise supported, risky, malformed and incomplete preview inputs."""
    failures: list[str] = []
    if not all(_classifies(action, kind) for action, kind in _KINDS.items()):
        failures.append("what-if classification regressed")
    invalid: tuple[object, ...] = (
        {},
        {"status": "Failed", "changes": []},
        {"unrelated": {"changes": []}},
        {"changes": [{}]},
        {"changes": [{"resourceId": "/example", "changeType": "Unknown"}]},
        {"changes": [], "properties": {"changes": []}},
    )
    wrong_types = ([], {"changes": None})
    if _accepts_any(invalid, analyze_whatif, ValueError) or _accepts_any(
        wrong_types, analyze_whatif, WhatIfInputTypeError
    ):
        failures.append("unsupported what-if result was accepted")
    malformed = ("{", '{"changes":[],"changes":[]}', "NaN")
    if _accepts_any(malformed, _read_object, ValueError):
        failures.append("malformed JSON was accepted")
    if any(analyze_whatif({"properties": {"changes": []}}).values()):
        failures.append("explicit empty preview must have zero changes")
    return failures


def main() -> int:
    """Emit valid summaries and fail explicitly for risks or unsupported input."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", "-f", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        sys.stderr.writelines(f"{failure}\n" for failure in failures)
        verdict = "failed" if failures else "passed"
        sys.stdout.write(f"Azure what-if reviewer self-test {verdict}.\n")
        return int(bool(failures))
    if args.file is None:
        parser.error("--file is required unless --self-test is selected")
    try:
        groups = _read(args.file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, WhatIfInputTypeError) as error:
        sys.stderr.write(f"Cannot review what-if: {error}\n")
        return _INVALID
    sys.stdout.write(
        f"{
            json.dumps(
                {
                    'summary': {key: len(items) for key, items in groups.items()},
                    'lists': groups,
                }
            )
        }\n"
    )
    if groups["delete"] or groups["recreate"] or groups["review"]:
        sys.stderr.write(
            "Destructive or unresolved changes require operator review; no deployment is authorized.\n"
        )
        return _DELETE if groups["delete"] else _REVIEW
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
