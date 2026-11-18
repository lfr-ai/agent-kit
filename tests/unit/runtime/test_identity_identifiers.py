"""Identifier parsing preserves value-free public failures and UUID semantics."""

import traceback

import pytest

from platform_kit_runtime.core.identity.models import canonical_uuid
from platform_kit_runtime.identity import IdentityConfig

_CANONICAL_ID = "abcdefab-cdef-4abc-8def-abcdefabcdef"
_MALFORMED_ID = "synthetic-private-identifier".replace("-", "").ljust(32, "x")


@pytest.mark.parametrize("identifier", [_MALFORMED_ID, "invalid-uuid"])
def test_malformed_uuid_traceback_does_not_expose_identifier(identifier: str) -> None:
    with pytest.raises(ValueError, match=r"^Invalid identity identifier\.$") as caught:
        canonical_uuid(identifier)

    assert type(caught.value) is ValueError
    assert identifier not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize("identifier", [_MALFORMED_ID, "invalid-uuid"])
@pytest.mark.parametrize("field", ["tenant_id", "client_id"])
def test_identity_config_traceback_does_not_expose_identifier(
    identifier: str, field: str
) -> None:
    with pytest.raises(ValueError, match=r"^Invalid identity identifier\.$") as caught:
        IdentityConfig(
            tenant_id=identifier if field == "tenant_id" else _CANONICAL_ID,
            client_id=identifier if field == "client_id" else _CANONICAL_ID,
            api_audience="api://offline",
            origin="https://app.test",
        )

    assert type(caught.value) is ValueError
    assert identifier not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "identifier", [_CANONICAL_ID, "00000000-0000-0000-0000-000000000000"]
)
def test_canonical_identifiers_remain_unchanged(identifier: str) -> None:
    assert canonical_uuid(identifier) == identifier
    config = IdentityConfig(
        tenant_id=identifier,
        client_id=identifier,
        api_audience="api://offline",
        origin="https://app.test",
    )
    assert config.tenant_id == identifier
    assert config.client_id == identifier


@pytest.mark.parametrize(
    "identifier", [_CANONICAL_ID.upper(), _CANONICAL_ID.replace("-", "")]
)
def test_uuid_parser_still_normalizes_noncanonical_identifiers(identifier: str) -> None:
    assert canonical_uuid(identifier) == _CANONICAL_ID


@pytest.mark.parametrize(
    "identifier", [_CANONICAL_ID.upper(), _CANONICAL_ID.replace("-", "")]
)
def test_identity_config_still_requires_canonical_identifiers(identifier: str) -> None:
    with pytest.raises(
        ValueError, match=r"^Identity identifiers must be canonical UUIDs\.$"
    ) as caught:
        IdentityConfig(
            tenant_id=identifier,
            client_id=_CANONICAL_ID,
            api_audience="api://offline",
            origin="https://app.test",
        )

    assert identifier not in "".join(traceback.format_exception(caught.value))
