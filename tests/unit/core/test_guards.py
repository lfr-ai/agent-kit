"""Narrowing helpers accept the documented shapes and reject every other type."""

import pytest

from agent_kit.core import guards
from agent_kit.core.errors import InputTypeError


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
