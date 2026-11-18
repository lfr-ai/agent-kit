"""Entra v2 signature validation with PyJWT and bounded, tenant-specific JWKS."""

import asyncio
import time

import jwt
from jwt.exceptions import PyJWTError

from platform_kit_runtime.core.identity.data import decode, mapping, strings, text
from platform_kit_runtime.core.identity.models import (
    CACHE_TTL_SECONDS,
    MAX_JSON_BYTES,
    MAX_TOKEN_BYTES,
    AuthenticationRequiredError,
    DependencyUnavailableError,
    IdentityConfig,
    IdentityError,
    Principal,
    UpstreamFailureError,
    canonical_uuid,
    finite_number,
)
from platform_kit_runtime.core.identity.ports import IdentityHTTP
from platform_kit_runtime.infrastructure.identity.upstream import check_upstream_status

_JWKS_REFRESH_COOLDOWN_SECONDS = 30
_SIGNING_ALGORITHM = "RS256"
_REQUIRED_CLAIMS = (
    "iss",
    "aud",
    "exp",
    "nbf",
    "iat",
    "tid",
    "oid",
    "sub",
)


class EntraJWTValidator:
    """Validate signatures before reading identity/permission claims."""

    def __init__(self, *, config: IdentityConfig, http: IdentityHTTP) -> None:
        """Bind fixed trust settings and bounded JWKS retrieval.

        Args:
            config (IdentityConfig): Fixed issuer, tenant and permitted audiences.
            http (IdentityHTTP): Caller-owned bounded JWKS transport.
        """
        self._config = config
        self._http = http
        self._keys: tuple[jwt.PyJWK, ...] = ()
        self._loaded_at = 0.0
        self._last_attempt: float | None = None
        self._last_failure: type[IdentityError] | None = None
        self._lock = asyncio.Lock()

    async def _load_keys(self) -> None:
        response = await self._http.get(
            url=f"{self._config.authority}/discovery/v2.0/keys",
            access_token=None,
            max_bytes=MAX_JSON_BYTES,
        )
        check_upstream_status(response.status)
        try:
            document = decode(response.content)
            self._check_key_issuers(document)
            keys = jwt.PyJWKSet.from_dict(document).keys
            accepted = tuple(
                key
                for key in keys
                if key.algorithm_name == _SIGNING_ALGORITHM
                and key.public_key_use in (None, "sig")
                and key.key_type == "RSA"
            )
            if not accepted:
                raise UpstreamFailureError
        except (ValueError, PyJWTError, KeyError) as error:
            raise UpstreamFailureError from error
        self._keys = accepted
        self._loaded_at = time.monotonic()

    async def _refresh_keys(self) -> None:
        self._last_attempt = time.monotonic()
        try:
            await self._load_keys()
        except IdentityError as error:
            # Retain only the safe error category, never exception tracebacks,
            # request tokens or upstream diagnostics between requests.
            self._last_failure = type(error)
            raise
        self._last_failure = None

    def _check_key_issuers(self, document: dict[str, object]) -> None:
        keys = document.get("keys")
        if not isinstance(keys, list):
            raise UpstreamFailureError
        for value in keys:
            issuer = mapping(value).get("issuer")
            if issuer is not None and (
                not isinstance(issuer, str)
                or issuer.replace("{tenantid}", self._config.tenant_id)
                != self._config.issuer
            ):
                raise UpstreamFailureError

    async def _key(self, kid: str) -> jwt.PyJWK:
        async with self._lock:
            now = time.monotonic()
            needs_refresh = now - self._loaded_at >= CACHE_TTL_SECONDS or not any(
                key.key_id == kid for key in self._keys
            )
            may_refresh = (
                self._last_attempt is None
                or now - self._last_attempt >= _JWKS_REFRESH_COOLDOWN_SECONDS
            )
            if needs_refresh and may_refresh:
                await self._refresh_keys()
            return self._cached_key(kid)

    def _cached_key(self, kid: str) -> jwt.PyJWK:
        if not self._keys or time.monotonic() - self._loaded_at >= CACHE_TTL_SECONDS:
            failure = self._last_failure or DependencyUnavailableError
            raise failure
        matches = tuple(key for key in self._keys if key.key_id == kid)
        if not matches and self._last_failure is not None:
            raise self._last_failure()
        if len(matches) != 1:
            raise AuthenticationRequiredError
        return matches[0]

    async def validate(self, *, token: str, audience: str) -> Principal:
        """Validate RS256, issuer, audience, times, tenant and identifier claims.

        Only the JOSE header is inspected before verification, to choose a key.
        Audience must be the configured API or BFF client. No token payload is
        decoded without signature validation; errors contain no token details.

        Args:
            token (str): Untrusted signed bearer or ID token.
            audience (str): Configured API audience or BFF client ID.

        Returns:
            Principal: Verified tenant/user identity and authorization claims.

        Raises:
            AuthenticationRequiredError: The token or any mandatory claim is invalid.
        """
        if len(token) > MAX_TOKEN_BYTES or audience not in (
            self._config.client_id,
            self._config.api_audience,
        ):
            raise AuthenticationRequiredError
        try:
            header = mapping(jwt.get_unverified_header(token))
            if header.get("alg") != _SIGNING_ALGORITHM or header.get("crit"):
                raise AuthenticationRequiredError
            key = await self._key(text(header.get("kid")))
            verified = mapping(
                jwt.decode(
                    token,
                    key=key,
                    algorithms=[_SIGNING_ALGORITHM],
                    audience=audience,
                    issuer=self._config.issuer,
                    options={"require": list(_REQUIRED_CLAIMS), "strict_aud": True},
                )
            )
            return self._principal(verified)
        except (PyJWTError, ValueError, KeyError, TypeError) as error:
            raise AuthenticationRequiredError from error

    def _principal(self, claims: dict[str, object]) -> Principal:
        tenant = canonical_uuid(text(claims.get("tid")))
        if tenant != self._config.tenant_id:
            raise AuthenticationRequiredError
        for name in ("exp", "nbf", "iat"):
            finite_number(claims.get(name))
        scopes = claims.get("scp", "")
        if not isinstance(scopes, str):
            raise AuthenticationRequiredError
        return Principal(
            tenant_id=tenant,
            subject_id=canonical_uuid(text(claims.get("oid"))),
            scopes=frozenset(scopes.split()),
            roles=strings(claims.get("roles", [])),
        )
