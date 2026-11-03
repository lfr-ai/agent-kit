"""Narrowing predicates and requirement helpers for decoded, untrusted values.

Decoded JSON and TOML arrive as ``object``. These helpers narrow them once, in
one place, so callers state the shape they expect instead of repeating
``isinstance`` chains and hand-written ``InputTypeError`` branches.
"""

from typing import TypeGuard, TypeIs

from agent_kit.core.errors import InputTypeError

type JsonObject = dict[str, object]


def is_json_object(value: object) -> TypeIs[JsonObject]:
    """Report whether ``value`` is a dict whose keys are all strings."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def is_nonempty_text(value: object) -> TypeGuard[str]:
    """Report whether ``value`` is a string with a non-whitespace character."""
    return isinstance(value, str) and bool(value.strip())


def is_str_list(value: object) -> TypeIs[list[str]]:
    """Report whether ``value`` is a list whose items are all strings."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def is_int(value: object) -> TypeGuard[int]:
    """Report whether ``value`` is an integer; ``bool`` is deliberately excluded."""
    return type(value) is int


def require_object(value: object, *, location: str) -> JsonObject:
    """Return ``value`` as a string-keyed object.

    Args:
        value (object): Decoded value to narrow.
        location (str): Safe field or document location for the diagnostic.

    Returns:
        JsonObject: ``value`` unchanged, now typed as ``dict[str, object]``.

    Raises:
        InputTypeError: ``value`` is not an object with string keys.
    """
    if is_json_object(value):
        return value
    raise InputTypeError(location=location, expected="an object")


def require_list(value: object, *, location: str) -> list[object]:
    """Return ``value`` as a list.

    Args:
        value (object): Decoded value to narrow.
        location (str): Safe field or document location for the diagnostic.

    Returns:
        list[object]: ``value`` unchanged, with untyped items.

    Raises:
        InputTypeError: ``value`` is not a list.
    """
    if isinstance(value, list):
        return value
    raise InputTypeError(location=location, expected="a list")


def require_text(value: object, *, location: str) -> str:
    """Return ``value`` as a string, rejecting every other type.

    Args:
        value (object): Decoded value to narrow.
        location (str): Safe field or document location for the diagnostic.

    Raises:
        InputTypeError: ``value`` is not a string.
    """
    if isinstance(value, str):
        return value
    raise InputTypeError(location=location, expected="a string")


def require_str_list(value: object, *, location: str) -> list[str]:
    """Return ``value`` as a list of strings.

    Args:
        value (object): Decoded value to narrow.
        location (str): Safe field or document location for the diagnostic.

    Returns:
        list[str]: ``value`` unchanged, now typed as strings.

    Raises:
        InputTypeError: ``value`` is not a list, or an item is not a string.
    """
    if is_str_list(value):
        return value
    raise InputTypeError(location=location, expected="a list of strings")


def require_int(value: object, *, location: str) -> int:
    """Return ``value`` as an integer, rejecting ``bool`` and every other type.

    Args:
        value (object): Decoded value to narrow.
        location (str): Safe field or document location for the diagnostic.

    Raises:
        InputTypeError: ``value`` is not an integer.
    """
    if is_int(value):
        return value
    raise InputTypeError(location=location, expected="an integer")
