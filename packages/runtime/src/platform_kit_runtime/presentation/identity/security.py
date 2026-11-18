"""Opt-in FastAPI guards; permission and CSRF checks never depend on proxy headers."""

from http import HTTPMethod
import secrets

from fastapi import Request

from platform_kit_runtime.core.identity.models import (
    OPAQUE_PATTERN,
    AuthenticationRequiredError,
    IdentityConfig,
    PermissionDeniedError,
    Principal,
    Session,
)
from platform_kit_runtime.core.identity.ports import BearerValidator, BrowserIdentity

_SAFE_METHODS = frozenset({HTTPMethod.GET, HTTPMethod.HEAD, HTTPMethod.OPTIONS})
_BEARER_SCHEME = "bearer"


def session_cookie(config: IdentityConfig) -> str:
    """Return the ``__Host-`` session cookie name, or the loopback-only variant."""
    return "__Host-pk-session" if config.secure_cookies else "pk-local-session"


def login_cookie(config: IdentityConfig) -> str:
    """Return the ``__Host-`` login-binding cookie name, or the loopback variant."""
    return "__Host-pk-login" if config.secure_cookies else "pk-local-login"


def require_origin(*, request: Request, config: IdentityConfig) -> None:
    """Require exactly one configured-origin header before accessing browser state.

    Args:
        request (Request): Untrusted incoming browser request.
        config (IdentityConfig): Fixed allowed origin, never inferred from headers.

    Raises:
        PermissionDeniedError: Origin is absent, duplicated or incorrect.
    """
    if request.headers.getlist("origin") != [config.origin]:
        raise PermissionDeniedError


def require_csrf(*, request: Request, session: Session, config: IdentityConfig) -> None:
    """Require exactly one fixed-origin header and the session's CSRF token.

    Args:
        request (Request): Untrusted incoming browser request.
        session (Session): Private authenticated state with the expected CSRF proof.
        config (IdentityConfig): Fixed allowed browser origin.

    Raises:
        PermissionDeniedError: Either proof is missing, duplicated or incorrect.
    """
    require_origin(request=request, config=config)
    proofs = request.headers.getlist("x-csrf-token")
    if len(proofs) != 1:
        raise PermissionDeniedError
    proof = proofs[0]
    if not OPAQUE_PATTERN.fullmatch(proof) or not secrets.compare_digest(
        proof, session.csrf_token
    ):
        raise PermissionDeniedError


class BearerGuard:
    """Callable FastAPI dependency requiring explicit, verified API permissions."""

    def __init__(
        self,
        *,
        config: IdentityConfig,
        validator: BearerValidator,
        scopes: frozenset[str],
        roles: frozenset[str],
    ) -> None:
        """Use ``config``/``validator`` and require every supplied scope and role.

        Args:
            config (IdentityConfig): Fixed API audience and trust policy.
            validator (BearerValidator): Signature-verifying token validation port.
            scopes (frozenset[str]): Every required delegated scope.
            roles (frozenset[str]): Every required application role.

        Raises:
            ValueError: Both ``scopes`` and ``roles`` are empty.
        """
        if not scopes and not roles:
            message = "Explicit identity permissions are required."
            raise ValueError(message)
        self._config = config
        self._validator = validator
        self._scopes = scopes
        self._roles = roles

    async def __call__(self, request: Request) -> Principal:
        """Validate the request's sole Bearer token and return a safe principal.

        Raises ``AuthenticationRequiredError`` for an absent, repeated or
        malformed authorization header. Validator and permission errors
        (``AuthenticationRequiredError``, ``PermissionDeniedError``,
        ``DependencyUnavailableError``, ``UpstreamFailureError``) propagate.
        """
        values = request.headers.getlist("authorization")
        if len(values) != 1:
            raise AuthenticationRequiredError
        scheme, separator, token = values[0].partition(" ")
        if (
            not separator
            or scheme.casefold() != _BEARER_SCHEME
            or not token
            or " " in token
        ):
            raise AuthenticationRequiredError
        principal = await self._validator.validate(
            token=token, audience=self._config.api_audience
        )
        principal.require(scopes=self._scopes, roles=self._roles)
        return principal


class SessionGuard:
    """Callable browser dependency; unsafe methods always require origin and CSRF."""

    def __init__(self, *, config: IdentityConfig, service: BrowserIdentity) -> None:
        """Bind fixed browser policy and the identity service.

        Args:
            config (IdentityConfig): Fixed browser origin and cookie policy.
            service (BrowserIdentity): Private session authentication use cases.
        """
        self._config = config
        self._service = service

    async def __call__(self, request: Request) -> Principal:
        """Return a safe principal, checking CSRF before refreshing a browser session.

        Unsafe methods require one configured ``Origin`` and the session's CSRF
        proof, otherwise ``PermissionDeniedError`` propagates. Session errors
        (``AuthenticationRequiredError``, ``DependencyUnavailableError``,
        ``UpstreamFailureError``) propagate from the identity service.
        """
        session_id = request.cookies.get(session_cookie(self._config))
        if request.method not in _SAFE_METHODS:
            require_origin(request=request, config=self._config)
            session = await self._service.session(session_id=session_id, refresh=False)
            require_csrf(request=request, session=session, config=self._config)
        authenticated = await self._service.session(session_id=session_id)
        return authenticated.tokens.principal
