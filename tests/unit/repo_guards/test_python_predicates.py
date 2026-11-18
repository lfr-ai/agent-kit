"""Full type predicates and partial validators keep distinct truth tables."""

from typing import TypeGuard, TypeIs, get_type_hints

import pytest

from agent_kit.application.catalog import documents
from agent_kit.core.errors import InputTypeError
from agent_kit.core.guards import JSONObject, is_json_object, require_list


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({}, True),
        ({"name": object(), "items": []}, True),
        ({1: "not a string key"}, False),
        ({"name": "mixed", 1: None}, False),
        ([], False),
        (None, False),
    ],
)
def test_mapping_predicates_cover_the_entire_target_type(
    value: object, expected: bool
) -> None:
    assert is_json_object(value) is expected
    assert get_type_hints(is_json_object)["return"] == TypeIs[JSONObject]


@pytest.mark.parametrize(
    ("value", "expected"),
    [([], True), ([None, "text", 1], True), ((), False), (None, False)],
)
def test_list_predicate_accepts_empty_and_heterogeneous_lists(
    value: object, expected: bool
) -> None:
    if expected:
        assert require_list(value, location="test") is value
    else:
        with pytest.raises(InputTypeError):
            require_list(value, location="test")
    assert get_type_hints(require_list)["return"] == list[object]


def test_partial_string_validators_do_not_claim_bidirectional_narrowing() -> None:
    assert documents.one_line("ok", 4)
    assert not documents.one_line("longer", 4)
    assert not documents.one_line("two\nlines", 20)
    assert documents.legal_skill_name("kit-example")
    assert not documents.legal_skill_name("Not a legal name")
    assert get_type_hints(documents.one_line)["return"] == TypeGuard[str]
    assert get_type_hints(documents.legal_skill_name)["return"] == TypeGuard[str]
