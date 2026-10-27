"""Closed-schema validation of declared composition selections."""

from __future__ import annotations

import pytest

from agent_kit.application.services.selection import (
    InvalidSelectionError,
    parse_selection,
)
from agent_kit.core.errors import InputTypeError
from agent_kit.core.models import Selection


def test_minimal_selection_defaults_lists_to_empty() -> None:
    selection = parse_selection({"schema_version": 1, "profile": "backend"})

    assert selection == Selection(
        profile="backend", features=(), runtimes=(), skills=()
    )


def test_full_selection_preserves_declared_order() -> None:
    selection = parse_selection(
        {
            "schema_version": 1,
            "profile": "fullstack",
            "features": ["terraform", "bicep"],
            "runtimes": ["copilot"],
            "skills": ["kit-tdd"],
        }
    )

    assert selection.features == ("terraform", "bicep")
    assert selection.runtimes == ("copilot",)
    assert selection.skills == ("kit-tdd",)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        pytest.param(
            {"profile": "backend"}, "schema_version is missing", id="no-version"
        ),
        pytest.param({"schema_version": 1}, "profile is missing", id="no-profile"),
        pytest.param(
            {"schema_version": 1, "profile": "backend", "cloud": "aws"},
            "cloud is not supported",
            id="unknown-field",
        ),
        pytest.param(
            {"schema_version": 2, "profile": "backend"},
            "schema_version must be 1",
            id="future-version",
        ),
        pytest.param(
            {"schema_version": True, "profile": "backend"},
            "schema_version must be 1",
            id="boolean-version",
        ),
        pytest.param(
            {"schema_version": 1, "profile": "  "},
            "profile must not be empty",
            id="blank-profile",
        ),
        pytest.param(
            {"schema_version": 1, "profile": "backend", "features": ["iac", "iac"]},
            "features must not repeat",
            id="repeated-feature",
        ),
        pytest.param(
            {"schema_version": 1, "profile": "backend", "skills": [""]},
            "skills must not contain empty",
            id="empty-skill",
        ),
    ],
)
def test_invalid_selection_values_are_rejected(
    document: dict[str, object], message: str
) -> None:
    with pytest.raises(InvalidSelectionError, match=message):
        parse_selection(document)


@pytest.mark.parametrize(
    "document",
    [
        pytest.param(["backend"], id="array-document"),
        pytest.param({"schema_version": 1, "profile": 3}, id="numeric-profile"),
        pytest.param(
            {"schema_version": 1, "profile": "backend", "features": "iac"},
            id="string-features",
        ),
        pytest.param(
            {"schema_version": 1, "profile": "backend", "runtimes": [1]},
            id="numeric-runtime",
        ),
    ],
)
def test_wrongly_typed_selection_is_rejected(document: object) -> None:
    with pytest.raises(InputTypeError):
        parse_selection(document)


def test_rejection_does_not_echo_untrusted_values() -> None:
    secret = "token-value-that-must-not-leak"

    with pytest.raises(InvalidSelectionError) as raised:
        parse_selection(
            {"schema_version": 1, "profile": "backend", "features": [secret, secret]}
        )

    assert secret not in str(raised.value)
