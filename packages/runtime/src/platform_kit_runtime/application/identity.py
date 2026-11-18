"""Browser flow, absolute-expiry sessions and private per-user Graph caching."""

import asyncio
from collections.abc import Callable
from dataclasses import replace
import hashlib
import secrets
import time

from platform_kit_runtime.core.identity.data import (
    decode,
    decode_session,
    encode,
    encode_session,
    text,
)
from platform_kit_runtime.core.identity.models import (
    LOGIN_TTL_SECONDS,
    OPAQUE_PATTERN,
    REFRESH_MARGIN_SECONDS,
    Authenticated,
    AuthenticationRequiredError,
    Avatar,
    DependencyUnavailableError,
    IdentityConfig,
    ImageType,
    InvalidCallbackError,
    Login,
    SafeProfile,
    Session,
    safe_return_path,
)
from platform_kit_runtime.core.identity.ports import (
    GraphReader,
    IdentityProvider,
    IdentityStore,
)

_LOCK_STRIPES = 64
_SECRET_BYTES = 32


def private_key(*, kind: str, identifier: str) -> str:
    """Return a namespaced hash key without raw credentials or user identifiers.

    Args:
        kind (str): Internal storage category.
        identifier (str): Private namespace and credential or identity material.

    Returns:
        str: Versioned category prefix followed by the identifier's SHA-256 digest.
    """
    digest = hashlib.sha256(identifier.encode()).hexdigest()
    return f"pk:identity:v1:{kind}:{digest}"


def _cookie_key(*, kind: str, value: str | None, namespace: str) -> str:
    if value is None or OPAQUE_PATTERN.fullmatch(value) is None:
        raise AuthenticationRequiredError
    return private_key(kind=kind, identifier=f"{namespace}:{value}")


class IdentityService:
    """Orchestrate injected ports without vendor or transport dependencies.

    Implements ``BrowserIdentity``, which documents the identity errors callers
    handle; port failures propagate unchanged.
    """

    def __init__(
        self,
        *,
        config: IdentityConfig,
        store: IdentityStore,
        provider: IdentityProvider,
        graph: GraphReader,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Bind explicit ports without creating external resources.

        Args:
            config (IdentityConfig): Fixed trust boundaries and TTL policy.
            store (IdentityStore): Caller-owned private atomic TTL store.
            provider (IdentityProvider): Caller-owned OIDC flow and refresh adapter.
            graph (GraphReader): Caller-owned allowlisted profile/photo reader.
            clock (Callable[[], float]): Epoch-seconds source for session expiry.
        """
        self.config = config
        self.store = store
        self.provider = provider
        self.graph = graph
        self._clock = clock
        self._namespace = hashlib.sha256(
            encode(
                {
                    "tenant": config.tenant_id,
                    "client": config.client_id,
                    "audience": config.api_audience,
                    "origin": config.origin,
                    "local": config.allow_insecure_loopback,
                    "session_ttl": config.session_ttl_seconds,
                    "cache_ttl": config.cache_ttl_seconds,
                }
            )
        ).hexdigest()
        self._cache_locks = tuple(asyncio.Lock() for _ in range(_LOCK_STRIPES))

    async def login(self, *, return_to: str) -> Login:
        """Return the provider redirect and a fresh browser binding for ``return_to``.

        ``safe_return_path`` raises ``InvalidCallbackError`` for an unsafe
        destination before any provider call.
        """
        destination = safe_return_path(return_to)
        flow = await self.provider.begin()
        binding = secrets.token_urlsafe(_SECRET_BYTES)
        await self.store.put(
            key=_cookie_key(kind="login", value=binding, namespace=self._namespace),
            value=encode({"flow": flow.flow, "return_to": destination}),
            ttl=LOGIN_TTL_SECONDS,
        )
        return Login(authorization_url=flow.authorization_url, binding=binding)

    async def callback(
        self, *, binding: str | None, state: str, code: str, previous: str | None
    ) -> Authenticated:
        """Consume browser-bound state once and rotate the session.

        Args:
            binding (str | None): Browser login-binding cookie, if present.
            state (str): Returned login state.
            code (str): One-time authorization code.
            previous (str | None): Previous session cookie to revoke, if valid.

        Returns:
            Authenticated: Fresh session cookie and original safe return path.

        Raises:
            InvalidCallbackError: Binding, state, nonce, code or PKCE is invalid.
            DependencyUnavailableError: Stored login data is malformed.
        """
        try:
            key = _cookie_key(kind="login", value=binding, namespace=self._namespace)
        except AuthenticationRequiredError as error:
            raise InvalidCallbackError from error
        raw = await self.store.take(key=key)
        if raw is None:
            raise InvalidCallbackError
        try:
            data = decode(raw)
            flow, destination = text(data.get("flow")), text(data.get("return_to"))
        except ValueError as error:
            raise DependencyUnavailableError from error
        tokens = await self.provider.complete(flow=flow, state=state, code=code)
        if tokens.principal.tenant_id != self.config.tenant_id:
            raise InvalidCallbackError
        if previous is not None and OPAQUE_PATTERN.fullmatch(previous):
            await self.logout(session_id=previous)
        session_id = secrets.token_urlsafe(_SECRET_BYTES)
        await self.store.put(
            key=_cookie_key(
                kind="session", value=session_id, namespace=self._namespace
            ),
            value=encode_session(
                Session(
                    tokens=tokens,
                    csrf_token=secrets.token_urlsafe(_SECRET_BYTES),
                    expires_at=self._clock() + self.config.session_ttl_seconds,
                )
            ),
            ttl=self.config.session_ttl_seconds,
        )
        return Authenticated(
            session_id=session_id, return_to=safe_return_path(destination)
        )

    async def cancel_login(self, *, binding: str | None) -> None:
        """Consume a malformed callback's pending login, if its cookie is valid."""
        if binding is not None and OPAQUE_PATTERN.fullmatch(binding):
            await self.store.take(
                key=_cookie_key(kind="login", value=binding, namespace=self._namespace)
            )

    async def session(self, *, session_id: str | None, refresh: bool = True) -> Session:
        """Load a session and optionally refresh tokens using existing-only CAS.

        Args:
            session_id (str | None): Opaque browser session cookie, if present.
            refresh (bool): Whether near-expiry tokens may be refreshed.

        Returns:
            Session: Private authenticated session with its original absolute expiry.

        Raises:
            AuthenticationRequiredError: Missing, expired, revoked or concurrently removed.
            DependencyUnavailableError: Stored session data is malformed.
        """
        key = _cookie_key(kind="session", value=session_id, namespace=self._namespace)
        raw = await self.store.get(key=key)
        if raw is None:
            raise AuthenticationRequiredError
        try:
            session = decode_session(raw)
        except ValueError as error:
            raise DependencyUnavailableError from error
        if (
            session.expires_at <= self._clock()
            or session.tokens.principal.tenant_id != self.config.tenant_id
        ):
            raise AuthenticationRequiredError
        if (
            not refresh
            or session.tokens.expires_at > self._clock() + REFRESH_MARGIN_SECONDS
        ):
            return session
        updated = replace(
            session, tokens=await self.provider.refresh(tokens=session.tokens)
        )
        ttl = int(session.expires_at - self._clock())
        if ttl <= 0 or not await self.store.replace(
            key=key, expected=raw, value=encode_session(updated), ttl=ttl
        ):
            raise AuthenticationRequiredError
        return updated

    async def logout(self, *, session_id: str) -> None:
        """Delete local state; the presentation caller must validate CSRF first."""
        await self.store.delete(
            key=_cookie_key(kind="session", value=session_id, namespace=self._namespace)
        )

    def _profile_key(self, *, session: Session, kind: str) -> str:
        principal = session.tokens.principal
        return private_key(
            kind=kind,
            identifier=f"{self._namespace}:{principal.tenant_id}:{principal.subject_id}",
        )

    def _lock(self, key: str) -> asyncio.Lock:
        return self._cache_locks[hash(key) % _LOCK_STRIPES]

    async def profile(self, *, session: Session) -> SafeProfile:
        """Return the cached or fetched allowlisted profile for ``session``.

        Malformed cached profile data raises ``DependencyUnavailableError``.
        """
        key = self._profile_key(session=session, kind="profile")
        async with self._lock(key):
            raw = await self.store.get(key=key)
            if raw is not None:
                try:
                    name = decode(raw).get("display_name")
                    return SafeProfile(
                        display_name=None if name is None else text(name)
                    )
                except ValueError as error:
                    raise DependencyUnavailableError from error
            result = await self.graph.profile(access_token=session.tokens.access_token)
            await self.store.put(
                key=key,
                value=encode({"display_name": result.display_name}),
                ttl=self.config.cache_ttl_seconds,
            )
            return result

    async def avatar(self, *, session: Session) -> Avatar | None:
        """Return the cached or fetched supported avatar, or ``None`` when absent.

        A missing photo is cached as well.
        """
        key = self._profile_key(session=session, kind="avatar")
        async with self._lock(key):
            raw = await self.store.get(key=key)
            if raw is not None:
                return _decode_avatar(raw)
            result = await self.graph.avatar(access_token=session.tokens.access_token)
            value = (
                result.media_type.encode() + b"\n" + result.content
                if result is not None
                else b""
            )
            await self.store.put(
                key=key, value=value, ttl=self.config.cache_ttl_seconds
            )
            return result


def _decode_avatar(raw: bytes) -> Avatar | None:
    if not raw:
        return None
    try:
        media_type, content = raw.split(b"\n", 1)
        return Avatar(content=content, media_type=ImageType(media_type.decode()))
    except ValueError as error:
        raise DependencyUnavailableError from error
