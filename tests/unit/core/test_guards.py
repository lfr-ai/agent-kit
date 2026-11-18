"""Narrowing helpers accept the documented shapes and reject every other type."""

import pytest

from agent_kit.core import guards
from agent_kit.core.errors import DuplicateJSONFieldError, InputTypeError


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({}, True),
        ({"a": 1}, True),
        ({1: "a"}, False),
        ([], False),
        ("a", False),
        (None, False),
    ],
)
def test_json_object_requires_string_keys(value: object, *, expected: bool) -> None:
    assert guards.is_json_object(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("a", True), (" a ", True), ("", False), ("  ", False), (1, False), (None, False)],
)
def test_nonempty_text_rejects_blank_and_non_strings(
    value: object, *, expected: bool
) -> None:
    assert guards.is_nonempty_text(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [([], True), (["a"], True), (["a", 1], False), ("a", False), (("a",), False)],
)
def test_str_list_requires_a_list_of_strings(value: object, *, expected: bool) -> None:
    assert guards.is_str_list(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"), [(1, True), (0, True), (True, False), (1.0, False)]
)
def test_int_excludes_bool(value: object, *, expected: bool) -> None:
    assert guards.is_int(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.2.3", True),
        ("0.1.0-rc.1", True),
        ("1.2.3+build.5", True),
        ("1.2", False),
        ("v1.2.3", False),
        ("1.2.3\n", False),
        (1, False),
    ],
)
def test_semantic_version_requires_three_numeric_parts(
    value: object, *, expected: bool
) -> None:
    assert guards.is_semantic_version(value) is expected


def test_unique_json_object_rejects_duplicate_json_field() -> None:
    """The shared JSON object hook must reject duplicate keys."""
    with pytest.raises(ValueError, match="duplicate JSON field"):
        guards.unique_json_object([("schema_version", 1), ("schema_version", 1)])


@pytest.mark.parametrize(
    ("require", "good", "bad", "expected"),
    [
        (guards.require_object, {"a": 1}, [], "an object"),
        (guards.require_list, [1], {}, "a list"),
        (guards.require_text, "a", 1, "a string"),
        (guards.require_str_list, ["a"], ["a", 1], "a list of strings"),
        (guards.require_int, 3, True, "an integer"),
    ],
    ids=["object", "list", "text", "str-list", "int"],
)
def test_require_returns_good_values_and_describes_bad_ones(
    require: object, good: object, bad: object, expected: str
) -> None:
    assert callable(require)
    assert require(good, location="doc.field") is good
    with pytest.raises(InputTypeError, match=f"doc.field must be {expected}"):
        require(bad, location="doc.field")


class _Count(int):
    """An integer subclass that exact-integer guards must reject."""


def test_unique_json_object_keeps_order_and_names_the_duplicate_field() -> None:
    assert list(guards.unique_json_object([("b", 1), ("a", 2)])) == ["b", "a"]
    with pytest.raises(DuplicateJSONFieldError) as caught:
        guards.unique_json_object([("a", 1), ("b", 2), ("a", 3)])
    assert caught.value.field == "a"


@pytest.mark.parametrize(
    ("require", "bad"),
    [
        (guards.require_object, None),
        (guards.require_object, {1: "a"}),
        (guards.require_list, ("a",)),
        (guards.require_text, None),
        (guards.require_text, b"a"),
        (guards.require_str_list, "ab"),
        (guards.require_str_list, None),
        (guards.require_int, False),
        (guards.require_int, 1.0),
        (guards.require_int, "1"),
        (guards.require_int, _Count(1)),
    ],
    ids=[
        "object-none",
        "object-int-key",
        "list-tuple",
        "text-none",
        "text-bytes",
        "str-list-string",
        "str-list-none",
        "int-false",
        "int-float",
        "int-text",
        "int-subclass",
    ],
)
def test_require_rejects_near_miss_shapes_at_the_given_location(
    require: object, bad: object
) -> None:
    assert callable(require)
    with pytest.raises(InputTypeError) as caught:
        require(bad, location="doc.field")
    assert caught.value.location == "doc.field"
