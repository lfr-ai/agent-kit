"""Negative regression tests for native delivery role parsing and model settings."""

from __future__ import annotations

import json

import pytest

from agent_kit.application.services.native_delivery import (
    InvalidNativeJsonError,
    _checked_runtimes,
    _model_settings,
    _object_pairs,
    render_native_agents,
)
from agent_kit.core.errors import DuplicateJsonFieldError

ASSET_PATH = ".apm/skills/kit-runtime/assets/agents.json"


@pytest.mark.parametrize(
    ("content", "cause_type"),
    [
        (b"\xff", UnicodeDecodeError),
        (b"{", json.JSONDecodeError),
        (b'{"roles":[],"roles":[]}', DuplicateJsonFieldError),
    ],
)
def test_invalid_native_json_retains_its_original_cause(
    content: bytes, cause_type: type[Exception]
) -> None:
    with pytest.raises(InvalidNativeJsonError, match="invalid JSON") as raised:
        render_native_agents({ASSET_PATH: content}, ("copilot",))

    assert isinstance(raised.value.__cause__, cause_type)


def _asset_bytes(obj: object) -> bytes:
    return json.dumps(obj).encode("utf-8")


@pytest.mark.parametrize(
    ("content", "error_type", "message"),
    [
        ([], TypeError, "must be an object"),
        ({"schema_version": 1}, ValueError, "is missing field"),
    ],
)
def test_non_mapping_and_missing_fields_in_native_asset_are_rejected(
    content: object, error_type: type[Exception], message: str
) -> None:
    """A native asset must be a JSON object with both schema_version and roles."""
    with pytest.raises(error_type, match=message):
        render_native_agents({ASSET_PATH: _asset_bytes(content)}, ("copilot",))


@pytest.mark.parametrize(
    ("description", "message"),
    [
        ("", "must be non-empty text"),
        ("\u0001control", "contains unsupported control characters"),
    ],
)
def test_role_description_text_validations_trigger_errors(
    description: str, message: str
) -> None:
    """Descriptions must be non-empty, visible text without control characters."""
    role = {
        "id": "kit-worker",
        "kind": "worker",
        "tier": "readonly",
        "description": description,
        "body": "body",
        "workers": [],
    }
    with pytest.raises(ValueError, match=message):
        render_native_agents(
            {ASSET_PATH: _asset_bytes({"schema_version": 1, "roles": [role]})},
            ("copilot",),
        )


@pytest.mark.parametrize(
    ("identifier", "message"),
    [
        ("bad id", "invalid role identifier"),
        ("kit-worker", "description must be a single line"),
    ],
)
def test_invalid_identifier_and_multiline_description_raise(
    identifier: str, message: str
) -> None:
    """Role identifiers must match the kit-<name> pattern and description must be single-line."""
    desc = "A single line." if identifier != "kit-worker" else "first line\nsecond line"
    role = {
        "id": identifier,
        "kind": "primary",
        "tier": "implementer",
        "description": desc,
        "body": "body",
        "workers": [],
    }
    with pytest.raises(ValueError, match=message):
        render_native_agents(
            {ASSET_PATH: _asset_bytes({"schema_version": 1, "roles": [role]})},
            ("copilot",),
        )


@pytest.mark.parametrize(
    ("role", "error_type", "message"),
    [
        (
            {
                "id": "kit-x",
                "kind": "primary",
                "tier": "readonly",
                "description": "d",
                "body": "b",
                "workers": "not-a-list",
            },
            TypeError,
            "workers must be a list",
        ),
        (
            {
                "id": "kit-x",
                "kind": "primary",
                "tier": "coordinator",
                "description": "d",
                "body": "b",
                "workers": ["kit-x", "kit-x"],
            },
            ValueError,
            "contains duplicate identifiers",
        ),
        (
            {
                "id": "kit-x",
                "kind": "worker",
                "tier": "coordinator",
                "description": "d",
                "body": "b",
                "workers": [],
            },
            ValueError,
            "worker roles cannot coordinate",
        ),
        (
            {
                "id": "kit-x",
                "kind": "primary",
                "tier": "coordinator",
                "description": "d",
                "body": "b",
                "workers": [],
            },
            ValueError,
            "coordinator must name required workers",
        ),
        (
            {
                "id": "kit-x",
                "kind": "primary",
                "tier": "implementer",
                "description": "d",
                "body": "b",
                "workers": ["kit-worker"],
            },
            ValueError,
            "workers are only allowed for coordinators",
        ),
    ],
)
def test_worker_list_and_coordinator_constraints_are_enforced(
    role: dict[str, object], error_type: type[Exception], message: str
) -> None:
    """Worker declarations must be lists, unique, and only present for coordinator tiers."""
    full = {"schema_version": 1, "roles": [role]}
    with pytest.raises(error_type, match=message):
        render_native_agents({ASSET_PATH: _asset_bytes(full)}, ("copilot",))


def test_object_pairs_rejects_duplicate_json_field() -> None:
    """The JSON loader used by native assets must reject duplicate keys."""
    with pytest.raises(ValueError, match="duplicate JSON field"):
        # emulate object_pairs_hook behavior that raises on duplicate keys
        _object_pairs([("schema_version", 1), ("schema_version", 1)])


def test_checked_runtimes_rejects_invalid_and_empty() -> None:
    """Runtime selection must be non-empty and contain only supported runtimes."""
    with pytest.raises(ValueError, match="runtime targets must be non-empty"):
        _checked_runtimes(())
    with pytest.raises(ValueError, match="runtime targets must be non-empty"):
        _checked_runtimes(("other",))


def test_model_settings_rejects_unknown_and_invalid_models() -> None:
    """Model settings must be a mapping with explicit provider declarations and valid values."""
    with pytest.raises(TypeError, match="models must be an object"):
        _model_settings([], "loc")
    with pytest.raises(ValueError, match="has unknown provider"):
        _model_settings({"unknown": {}}, "loc")
    with pytest.raises(ValueError, match="must not be empty"):
        _model_settings({}, "loc")
    with pytest.raises(ValueError, match=r"models\.copilot must be a non-empty list"):
        _model_settings({"copilot": []}, "loc")
    with pytest.raises(TypeError, match=r"copilot.*must be strings"):
        _model_settings({"copilot": [1]}, "loc")
    with pytest.raises(ValueError, match="contains duplicate models"):
        _model_settings({"copilot": ["GPT-5 mini", "GPT-5 mini"]}, "loc")
    with pytest.raises(ValueError, match="unsupported Copilot model"):
        _model_settings({"copilot": ["Unknown Model"]}, "loc")
    with pytest.raises(ValueError, match="unsupported Claude model"):
        _model_settings({"claude": "bad"}, "loc")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 1),
        ("kind", []),
        ("tier", False),
        ("description", 1),
        ("body", {}),
        ("workers", [1]),
        ("models", []),
        ("models", {"copilot": "GPT-5 mini"}),
        ("models", {"copilot": [1]}),
        ("models", {"claude": ["haiku"]}),
    ],
)
def test_wrong_role_field_types_are_distinct_from_invalid_values(
    field: str, value: object
) -> None:
    role: dict[str, object] = {
        "id": "kit-reader",
        "kind": "worker",
        "tier": "readonly",
        "description": "Read the source.",
        "body": "Inspect files.",
        "workers": [],
    }
    role[field] = value
    with pytest.raises(TypeError, match="must be"):
        render_native_agents(
            {ASSET_PATH: _asset_bytes({"schema_version": 1, "roles": [role]})},
            ("copilot",),
        )


@pytest.mark.parametrize("version", [True, "1", None])
def test_schema_version_requires_an_integer_not_boolean(version: object) -> None:
    with pytest.raises(TypeError, match="schema_version must be an integer"):
        render_native_agents(
            {ASSET_PATH: _asset_bytes({"schema_version": version, "roles": []})},
            ("copilot",),
        )
