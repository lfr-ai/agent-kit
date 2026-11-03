"""Validate a declared composition selection against its closed schema."""

from __future__ import annotations

from agent_kit.core.guards import (
    JsonObject,
    is_int,
    require_list,
    require_object,
    require_text,
)
from agent_kit.core.models import Selection

_SCHEMA_VERSION = 1
_REQUIRED = frozenset({"schema_version", "profile"})
_LISTS = ("features", "runtimes", "skills")
_FIELDS = _REQUIRED | frozenset(_LISTS)


class InvalidSelectionError(ValueError):
    """A selection document violates its schema."""

    def __init__(self, *, field: str, rule: str) -> None:
        """Describe the violation without echoing untrusted values.

        Args:
            field (str): Schema field, or field names, that failed.
            rule (str): Safe description of the failed rule.
        """
        self.field = field
        self.rule = rule
        super().__init__(f"selection {field} {rule}")


def _names(value: object, field: str) -> tuple[str, ...]:
    """Require a list of unique, non-empty names.

    A field that is not a list of strings raises ``InputTypeError``.

    Args:
        value (object): Decoded list field.
        field (str): Schema field name used in diagnostics.

    Returns:
        tuple[str, ...]: The names in declaration order.

    Raises:
        InvalidSelectionError: A name is empty or repeated.
    """
    names: list[str] = []
    for entry in require_list(value, location=f"selection.{field}"):
        item = require_text(entry, location=f"selection.{field} entry")
        if not item.strip():
            raise InvalidSelectionError(
                field=field, rule="must not contain empty names"
            )
        names.append(item)
    if len(set(names)) != len(names):
        raise InvalidSelectionError(field=field, rule="must not repeat a name")
    return tuple(names)


def _check_header(value: JsonObject) -> str:
    """Require exactly the known fields, the current version, and a profile.

    A non-string profile raises ``InputTypeError``.

    Args:
        value (JsonObject): Decoded selection document.

    Returns:
        str: The non-empty profile name.

    Raises:
        InvalidSelectionError: Fields are missing or unknown, or a value is invalid.
    """
    missing = sorted(_REQUIRED - value.keys())
    if missing:
        raise InvalidSelectionError(field=", ".join(missing), rule="is missing")
    unknown = sorted(value.keys() - _FIELDS)
    if unknown:
        raise InvalidSelectionError(field=", ".join(unknown), rule="is not supported")
    version = value["schema_version"]
    if not is_int(version) or version != _SCHEMA_VERSION:
        raise InvalidSelectionError(field="schema_version", rule="must be 1")
    profile = require_text(value["profile"], location="selection.profile")
    if not profile.strip():
        raise InvalidSelectionError(field="profile", rule="must not be empty")
    return profile


def parse_selection(value: object) -> Selection:
    """Validate a decoded selection document.

    A document or field of the wrong type raises ``InputTypeError``; missing or
    unknown fields and invalid values raise ``InvalidSelectionError``.

    Args:
        value (object): Decoded JSON document.

    Returns:
        Selection: The validated selection; omitted lists are empty.
    """
    document = require_object(value, location="selection")
    profile = _check_header(document)
    features, runtimes, skills = (
        _names(document.get(field, []), field) for field in _LISTS
    )
    return Selection(
        profile=profile, features=features, runtimes=runtimes, skills=skills
    )
