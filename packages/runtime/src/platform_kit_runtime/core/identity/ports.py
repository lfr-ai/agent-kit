"""Provider-neutral identity boundaries and explicit failure contracts."""

from dataclasses import dataclass, field
from typing import Protocol

from platform_kit_runtime.core.identity.models import (
    Authenticated,
    Avatar,
    Login,
    Principal,
    ProviderLogin,
    ProviderTokens,
    SafeProfile,
    Session,
)


class IdentityStore(Protocol):
    """Private TTL store; operations may raise ``DependencyUnavailableError``."""

    async def get(self, *, key: str) -> bytes | None:
        """Return the private bytes at ``key``, or ``None`` if absent or expired.

        Raises ``DependencyUnavailableError`` when the read cannot complete.
        """
        ...

    async def put(self, *, key: str, value: bytes, ttl: int) -> None:
        """Store private state with expiry.

        Args:
            key (str): Namespaced private storage key.
            value (bytes): Private serialized state.
            ttl (int): Positive lifetime in seconds.

        Raises:
            DependencyUnavailableError: The write could not be confirmed.
        """
        ...

    async def take(self, *, key: str) -> bytes | None:
        """Atomically return and delete the bytes at ``key`` once, or ``None``.

        Raises ``DependencyUnavailableError`` when consumption cannot be
        confirmed.
        """
        ...

    async def delete(self, *, key: str) -> None:
        """Idempotently delete ``key`` without creating a tombstone.

        Raises ``DependencyUnavailableError`` when deletion cannot be confirmed.
        """
        ...

    async def replace(
        self, *, key: str, expected: bytes, value: bytes, ttl: int
    ) -> bool:
        """Atomically update only an existing key equal to ``expected``.

        Return False after expiry, logout or a competing refresh. Never create
        a missing key. The comparison and TTL update must be one atomic command.

        Args:
            key (str): Namespaced session key.
            expected (bytes): Previously read serialized state.
            value (bytes): Replacement private state.
            ttl (int): Positive remaining absolute lifetime in seconds.

        Returns:
            bool: Whether the matching existing state was replaced.

        Raises:
            DependencyUnavailableError: The atomic update could not be confirmed.
        """
        ...


class IdentityProvider(Protocol):
    """Confidential OIDC flow with PKCE, state and nonce validated by the SDK.

    Outages raise ``DependencyUnavailableError``; malformed responses raise
    ``UpstreamFailureError``. Never expose tokens, caches or flows to the browser.
    """

    async def begin(self) -> ProviderLogin:
        """Return a fresh SDK login flow, including PKCE, state and nonce.

        Raises ``DependencyUnavailableError`` when the provider is unavailable
        and ``UpstreamFailureError`` when discovery or flow data is malformed.
        """
        ...

    async def complete(self, *, flow: str, state: str, code: str) -> ProviderTokens:
        """Redeem a bound authorization code once.

        Args:
            flow (str): Private serialized login flow.
            state (str): Returned browser state.
            code (str): One-time authorization code.

        Returns:
            ProviderTokens: Verified principal and server-only token/cache state.

        Raises:
            InvalidCallbackError: Code or login proof is invalid.
            DependencyUnavailableError: Provider or signing keys are unavailable.
            UpstreamFailureError: The upstream response is malformed.
        """
        ...

    async def refresh(self, *, tokens: ProviderTokens) -> ProviderTokens:
        """Return refreshed private token state for the same identity.

        Raises ``AuthenticationRequiredError`` when the grant is revoked or the
        identity changed, ``DependencyUnavailableError`` when the provider or
        signing keys are unavailable, and ``UpstreamFailureError`` for a
        malformed upstream response.
        """
        ...


class BearerValidator(Protocol):
    """Signature and claim validation boundary; never merely decode claims."""

    async def validate(self, *, token: str, audience: str) -> Principal:
        """Validate a token's signature and mandatory trust claims.

        Args:
            token (str): Untrusted bearer or ID token.
            audience (str): Explicit expected audience.

        Returns:
            Principal: Verified identity and authorization claims.

        Raises:
            AuthenticationRequiredError: The token or audience is invalid.
            DependencyUnavailableError: Signing keys are unavailable.
            UpstreamFailureError: Key discovery is malformed or oversized.
        """
        ...


class GraphReader(Protocol):
    """Server-only profile API; dependency failures use identity errors."""

    async def profile(self, *, access_token: str) -> SafeProfile:
        """Return only allowlisted profile fields, without raw upstream data.

        Raises ``AuthenticationRequiredError`` when Graph rejects the token,
        ``DependencyUnavailableError`` when Graph is unavailable, and
        ``UpstreamFailureError`` for an unsafe response.
        """
        ...

    async def avatar(self, *, access_token: str) -> Avatar | None:
        """Return a bounded supported image, or ``None`` for a missing photo.

        Raises ``AuthenticationRequiredError`` when Graph rejects the token,
        ``DependencyUnavailableError`` when Graph is unavailable, and
        ``UpstreamFailureError`` for an unsafe response.
        """
        ...


class ClientAssertion(Protocol):
    """Consumer-owned workload federation/certificate assertion supplier."""

    def __call__(self) -> str:
        """Return a current signed assertion when MSAL sends a token request.

        Called synchronously in a worker thread, including on refresh; do not
        capture a one-time expiring token at application startup. Consumers may
        use a managed-identity token for the configured federation audience,
        and must translate acquisition outages into
        ``DependencyUnavailableError`` chained from the credential SDK error.
        """
        ...


@dataclass(frozen=True, kw_only=True, slots=True)
class IdentityHTTPResponse:
    """A bounded upstream response, never a browser response.

    Attributes:
        status (int): Upstream HTTP status.
        content (bytes): Bounded private body; omitted from repr.
        content_type (str): Media type without parameters.
    """

    status: int
    content: bytes = field(repr=False)
    content_type: str


class IdentityHTTP(Protocol):
    """Bounded GET transport; no redirect following or ambient credentials."""

    async def get(
        self, *, url: str, access_token: str | None, max_bytes: int
    ) -> IdentityHTTPResponse:
        """Fetch an upstream resource with a bounded response.

        Args:
            url (str): Explicit upstream URL.
            access_token (str | None): Private bearer credential, or no credential.
            max_bytes (int): Maximum permitted response body size.

        Returns:
            IdentityHTTPResponse: Status, bounded bytes and media type.

        Raises:
            DependencyUnavailableError: Transport, timeout or protocol failure.
            UpstreamFailureError: The response is compressed or oversized.
        """
        ...


class BrowserIdentity(Protocol):
    """Application-facing browser operations; propagate explicit identity errors."""

    async def login(self, *, return_to: str) -> Login:
        """Return the provider redirect and an opaque binding for ``return_to``.

        Raises ``InvalidCallbackError`` for an unsafe destination,
        ``DependencyUnavailableError`` when the store or provider is
        unavailable, and ``UpstreamFailureError`` for malformed discovery.
        """
        ...

    async def callback(
        self, *, binding: str | None, state: str, code: str, previous: str | None
    ) -> Authenticated:
        """Consume proof once and rotate the session.

        Args:
            binding (str | None): Browser login-binding cookie, if present.
            state (str): Returned login state.
            code (str): One-time authorization code.
            previous (str | None): Previous session cookie to revoke, if valid.

        Returns:
            Authenticated: New opaque session cookie and safe return destination.

        Raises:
            InvalidCallbackError: Binding, proof or destination is invalid.
            DependencyUnavailableError: Private state or provider is unavailable.
            UpstreamFailureError: The provider response is malformed.
        """
        ...

    async def cancel_login(self, *, binding: str | None) -> None:
        """Consume the pending login of a malformed callback's valid ``binding``.

        Raises ``DependencyUnavailableError`` when the store cannot confirm
        consumption.
        """
        ...

    async def session(self, *, session_id: str | None, refresh: bool = True) -> Session:
        """Authenticate from private state, optionally refreshing by CAS.

        Args:
            session_id (str | None): Opaque browser session cookie.
            refresh (bool): Whether expiring tokens may be refreshed.

        Returns:
            Session: Private authenticated session, never a browser response.

        Raises:
            AuthenticationRequiredError: Session is invalid, expired or removed.
            DependencyUnavailableError: Private state or provider is unavailable.
            UpstreamFailureError: Refresh returned malformed data.
        """
        ...

    async def logout(self, *, session_id: str) -> None:
        """Delete the session ``session_id`` after the caller has checked CSRF.

        Raises ``AuthenticationRequiredError`` for a malformed cookie and
        ``DependencyUnavailableError`` when deletion cannot be confirmed.
        """
        ...

    async def profile(self, *, session: Session) -> SafeProfile:
        """Return the cached or newly fetched allowlisted profile.

        Raises ``AuthenticationRequiredError`` when Graph rejects the
        credential, ``DependencyUnavailableError`` when the cache or Graph is
        unavailable, and ``UpstreamFailureError`` for unsafe Graph data.
        """
        ...

    async def avatar(self, *, session: Session) -> Avatar | None:
        """Return the cached or fetched supported image, or ``None`` when absent.

        Raises ``AuthenticationRequiredError`` when Graph rejects the
        credential, ``DependencyUnavailableError`` when the cache or Graph is
        unavailable, and ``UpstreamFailureError`` for unsafe image data.
        """
        ...
