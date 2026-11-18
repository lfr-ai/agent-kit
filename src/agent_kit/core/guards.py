"""Narrowing predicates and requirement helpers for decoded, untrusted values.

Decoded JSON and TOML arrive as ``object``. These helpers narrow them once, in
one place, so callers state the shape they expect instead of repeating
``isinstance`` chains and hand-written ``InputTypeError`` branches.
The ``require_*`` helpers return the input without coercion; invalid shapes
raise ``InputTypeError`` using the caller-supplied, safe ``location`` label.
"""

import re
from typing import TypeGuard, TypeIs

from agent_kit.core.errors import DuplicateJSONFieldError, InputTypeError

type JSONObject = dict[str, object]

_SEMANTIC_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?\Z")


def is_json_object(value: object) -> TypeIs[JSONObject]:
    """Recognize dictionaries whose keys are all strings."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def unique_json_object(pairs: list[tuple[str, object]]) -> JSONObject:
    """Merge ``pairs`` in order; a repeated key raises ``DuplicateJSONFieldError``.

    Serves as the ``object_pairs_hook`` for strict JSON decoding.
    """
    result: JSONObject = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONFieldError(key)
        result[key] = value
    return result


def is_nonempty_text(value: object) -> TypeGuard[str]:
    """Recognize strings containing at least one non-whitespace character."""
    return isinstance(value, str) and bool(value.strip())


def is_str_list(value: object) -> TypeIs[list[str]]:
    """Recognize lists of strings, including the empty list."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def is_int(value: object) -> TypeGuard[int]:
    """Recognize exact integers, excluding booleans and integer subclasses."""
    return type(value) is int


def is_semantic_version(value: object) -> TypeGuard[str]:
    """Recognize a ``MAJOR.MINOR.PATCH`` version string with optional suffix."""
    return isinstance(value, str) and _SEMANTIC_VERSION.fullmatch(value) is not None


def require_object(value: object, *, location: str) -> JSONObject:
    """Return a string-keyed dictionary unchanged, or raise ``InputTypeError``."""
    if is_json_object(value):
        return value
    raise InputTypeError(location=location, expected="an object")


def require_list(value: object, *, location: str) -> list[object]:
    """Return a list unchanged, or raise ``InputTypeError``."""
    if isinstance(value, list):
        return value
    raise InputTypeError(location=location, expected="a list")


def require_text(value: object, *, location: str) -> str:
    """Return any string unchanged, or raise ``InputTypeError``."""
    if isinstance(value, str):
        return value
    raise InputTypeError(location=location, expected="a string")


def require_str_list(value: object, *, location: str) -> list[str]:
    """Return a list of strings unchanged, or raise ``InputTypeError``."""
    if is_str_list(value):
        return value
    raise InputTypeError(location=location, expected="a list of strings")


def require_int(value: object, *, location: str) -> int:
    """Return an exact integer, not ``bool``, or raise ``InputTypeError``."""
    if is_int(value):
        return value
    raise InputTypeError(location=location, expected="an integer")
