"""Strict parsing helpers and private Redis serialization."""

import json

from platform_kit_runtime.core.identity.models import (
    Principal,
    ProviderTokens,
    Session,
    canonical_uuid,
    finite_number,
)


def mapping(value: object) -> dict[str, object]:
    """Return ``value`` as a string-keyed mapping; raise ``ValueError`` otherwise.

    Unknown field values are kept for later boundary-specific validation.
    """
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        message = "Invalid identity object."
        raise ValueError(message)
    return {key: item for key, item in value.items() if isinstance(key, str)}


def text(value: object) -> str:
    """Return ``value`` if it is a nonempty string; raise ``ValueError`` otherwise."""
    if not isinstance(value, str) or not value:
        message = "Invalid identity text."
        raise ValueError(message)
    return value


def strings(value: object) -> frozenset[str]:
    """Return a list of nonempty strings as a set; raise ``ValueError`` otherwise."""
    if not isinstance(value, list) or any(not item for item in value):
        message = "Invalid identity list."
        raise ValueError(message)
    return frozenset(text(item) for item in value)


def encode(value: dict[str, object]) -> bytes:
    """Encode a private object as compact UTF-8 JSON, rejecting non-finite numbers."""
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode()


def decode(value: bytes | str) -> dict[str, object]:
    """Decode a string-keyed JSON object; invalid input raises ``ValueError``."""
    return mapping(json.loads(value))


def principal_data(principal: Principal) -> dict[str, object]:
    """Return verified identity fields with sorted scopes and roles for the store."""
    return {
        "tenant_id": principal.tenant_id,
        "subject_id": principal.subject_id,
        "scopes": sorted(principal.scopes),
        "roles": sorted(principal.roles),
    }


def encode_session(session: Session) -> bytes:
    """Serialize a private session; never use this for an HTTP response."""
    return encode(
        {
            "principal": principal_data(session.tokens.principal),
            "access_token": session.tokens.access_token,
            "cache": session.tokens.cache,
            "token_expires_at": session.tokens.expires_at,
            "csrf_token": session.csrf_token,
            "expires_at": session.expires_at,
        }
    )


def decode_session(value: bytes) -> Session:
    """Return the validated server-only session; raise ``ValueError`` if malformed.

    Malformed JSON, encoding, identifiers, times or any required field fail.
    """
    data = decode(value)
    principal = mapping(data.get("principal"))
    return Session(
        tokens=ProviderTokens(
            principal=Principal(
                tenant_id=canonical_uuid(text(principal.get("tenant_id"))),
                subject_id=canonical_uuid(text(principal.get("subject_id"))),
                scopes=strings(principal.get("scopes")),
                roles=strings(principal.get("roles")),
            ),
            access_token=text(data.get("access_token")),
            cache=text(data.get("cache")),
            expires_at=finite_number(data.get("token_expires_at")),
        ),
        csrf_token=text(data.get("csrf_token")),
        expires_at=finite_number(data.get("expires_at")),
    )
