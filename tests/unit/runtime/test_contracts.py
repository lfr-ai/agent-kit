"""Characterize wire values and safety invariants before internal relocation."""

from enum import StrEnum
from urllib.parse import quote

from hypothesis import given
from hypothesis import strategies as st
import pytest

from platform_kit_runtime.ai import AIFinishReason, AIRole
from platform_kit_runtime.application.readiness import ReadinessFailure
from platform_kit_runtime.core.identity.data import decode_session, encode_session
from platform_kit_runtime.core.identity.models import (
    InvalidCallbackError,
    safe_return_path,
)
from platform_kit_runtime.identity import ImageType
from platform_kit_runtime.presentation.health import HealthStatus
from platform_kit_runtime.presentation.identity.problems import IdentityProblemCode
from platform_kit_runtime.presentation.problems import ProblemCode


@pytest.mark.parametrize(
    ("enum", "values"),
    [
        (AIRole, ("system", "user", "assistant")),
        (AIFinishReason, ("stop", "length")),
        (ImageType, ("image/jpeg", "image/png")),
        (ReadinessFailure, ("probe_failed", "timeout")),
        (HealthStatus, ("ok", "ready")),
        (
            IdentityProblemCode,
            (
                "invalid_callback",
                "authentication_required",
                "permission_denied",
                "identity_unavailable",
                "identity_upstream_failure",
                "avatar_missing",
                "identity_internal_error",
            ),
        ),
        (
            ProblemCode,
            (
                "not_ready",
                "invalid_request",
                "not_found",
                "method_not_allowed",
                "http_error",
                "internal_error",
                "rate_limited",
            ),
        ),
    ],
)
def test_closed_enum_wire_values(enum: type[StrEnum], values: tuple[str, ...]) -> None:
    assert tuple(member.value for member in enum) == values
    assert len(enum.__members__) == len(values)


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-._~", max_size=80))
def test_safe_return_paths_preserve_original_text(segment: str) -> None:
    path = f"/{segment}?tab=one#section"
    assert safe_return_path(path) == path


@given(
    st.sampled_from(["\\", "%", "\x00", "\n", "\r", "\t", "\x7f"]),
    st.integers(min_value=0, max_value=3),
)
def test_unsafe_return_characters_remain_rejected(
    character: str, encoding_depth: int
) -> None:
    for _ in range(encoding_depth):
        character = quote(character, safe="")
    with pytest.raises(InvalidCallbackError):
        safe_return_path(f"/path{character}tail")


def test_private_session_encoding_is_stable() -> None:
    raw = (
        b'{"principal":{"tenant_id":"11111111-1111-4111-8111-111111111111",'
        b'"subject_id":"33333333-3333-4333-8333-333333333333",'
        b'"scopes":["read","write"],"roles":["Reader"]},'
        b'"access_token":"private-access","cache":"private-cache",'
        b'"token_expires_at":1234.0,"csrf_token":"private-proof","expires_at":2345.0}'
    )
    session = decode_session(raw)
    assert encode_session(session) == raw
    assert "private" not in repr(session)


@pytest.mark.parametrize(
    "value",
    [
        b"null",
        b"[]",
        b"{}",
        b"\xff",
        b'{"principal":true}',
        b'{"principal":{"tenant_id":"bad"}}',
    ],
)
def test_malformed_private_sessions_are_rejected(value: bytes) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - assert shared decoder error type
        decode_session(value)
