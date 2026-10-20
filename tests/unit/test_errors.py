"""Stable structured input errors shared by the runtime layers."""

from agent_kit.core.errors import DuplicateJsonFieldError, InputTypeError


def test_input_type_failure_has_context_without_inheriting_value_error() -> None:
    error = InputTypeError(location="session context input", expected="an object")

    assert isinstance(error, TypeError)
    assert not isinstance(error, ValueError)
    assert error.location == "session context input"
    assert error.expected == "an object"
    assert error.args == ("session context input must be an object",)


def test_duplicate_json_field_preserves_value_error_and_key_context() -> None:
    error = DuplicateJsonFieldError("schema_version")

    assert isinstance(error, ValueError)
    assert error.field == "schema_version"
    assert error.args == ("duplicate JSON field 'schema_version'",)
