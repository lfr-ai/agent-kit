"""Validate a declared composition selection against its closed schema."""

from __future__ import annotations

from typing import TypeGuard

from agent_kit.core.errors import InputTypeError
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


def _mapping(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow decoded JSON to a string-keyed object."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _names(value: object, field: str) -> tuple[str, ...]:
    """Require a list of unique, non-empty names.

    Raises:
        InputTypeError: The field is not a list of strings.
        InvalidSelectionError: A name is empty or repeated.
    """
    if not isinstance(value, list):
        raise InputTypeError(location=f"selection.{field}", expected="a list")
    names: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise InputTypeError(
                location=f"selection.{field} entry", expected="a string"
            )
        if not item.strip():
            raise InvalidSelectionError(
                field=field, rule="must not contain empty names"
            )
        names.append(item)
    if len(set(names)) != len(names):
        raise InvalidSelectionError(field=field, rule="must not repeat a name")
    return tuple(names)


def _check_header(value: dict[str, object]) -> str:
    """Require exactly the known fields, the current version, and a profile.

    Raises:
        InputTypeError: The profile is not a string.
        InvalidSelectionError: Fields are missing or unknown, or a value is invalid.
    """
    missing = sorted(_REQUIRED - value.keys())
    if missing:
        raise InvalidSelectionError(field=", ".join(missing), rule="is missing")
    unknown = sorted(value.keys() - _FIELDS)
    if unknown:
        raise InvalidSelectionError(field=", ".join(unknown), rule="is not supported")
    version = value["schema_version"]
    if type(version) is not int or version != _SCHEMA_VERSION:
        raise InvalidSelectionError(field="schema_version", rule="must be 1")
    profile = value["profile"]
    if not isinstance(profile, str):
        raise InputTypeError(location="selection.profile", expected="a string")
    if not profile.strip():
        raise InvalidSelectionError(field="profile", rule="must not be empty")
    return profile


def parse_selection(value: object) -> Selection:
    """Validate a decoded selection document.

    Args:
        value (object): Decoded JSON document.

    Returns:
        Selection: The validated selection; omitted lists are empty.

    Raises:
        InputTypeError: The document or a field has the wrong type.
        InvalidSelectionError: Fields are missing or unknown, or a value is invalid.
    """
    if not _mapping(value):
        raise InputTypeError(location="selection", expected="an object")
    profile = _check_header(value)
    features, runtimes, skills = (
        _names(value.get(field, []), field) for field in _LISTS
    )
    return Selection(
        profile=profile, features=features, runtimes=runtimes, skills=skills
    )
