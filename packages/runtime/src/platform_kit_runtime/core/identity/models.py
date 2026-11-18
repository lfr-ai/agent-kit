"""Identity records, safe configuration and policy; no framework or provider SDK."""

from dataclasses import dataclass, field
from enum import StrEnum, unique
import ipaddress
import math
import re
from typing import Final
from urllib.parse import SplitResult, unquote, urlsplit
from uuid import UUID

from platform_kit_runtime.core.validation import (
    URLScheme,
    is_int_in_range,
    is_loopback_host,
)

LOGIN_TTL_SECONDS: Final[int] = 300
_SESSION_TTL_SECONDS = 3600
_MAX_SESSION_TTL_SECONDS = 86400
CACHE_TTL_SECONDS: Final[int] = 300
_MAX_CACHE_TTL_SECONDS = 900
MAX_AVATAR_BYTES: Final[int] = 262144
MAX_JSON_BYTES: Final[int] = 65536
MAX_TOKEN_BYTES: Final[int] = 16384
MAX_NAME_LENGTH: Final[int] = 256
REFRESH_MARGIN_SECONDS: Final[int] = 60
_DEFAULT_HTTP_PORT = 80
_DEFAULT_HTTPS_PORT = 443
_MAX_HOSTNAME_LENGTH = 253
OPAQUE_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_-]{43}")
_NUMERIC_HOST_LABEL = re.compile(r"(?:[0-9]+|0x[0-9a-f]+)", re.IGNORECASE)
_HOSTNAME_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HOSTNAME_TEXT = re.compile(rf"{_HOSTNAME_LABEL}(?:\.{_HOSTNAME_LABEL})*\.?")
_INVALID_ORIGIN_MESSAGE = "Invalid identity origin."
_INVALID_ORIGIN_PORT_MESSAGE = "Invalid identity origin port."


class IdentityError(Exception):
    """Base for sanitized, explicitly handled identity failures."""


class InvalidCallbackError(IdentityError):
    """The login, callback, browser binding or return destination is invalid."""


class AuthenticationRequiredError(IdentityError):
    """Credentials are absent, expired, revoked or invalid; fail closed."""


class PermissionDeniedError(IdentityError):
    """An authenticated identity lacks required permissions or CSRF proof."""


class DependencyUnavailableError(IdentityError):
    """The identity store or upstream is unavailable; no fallback is allowed."""


class UpstreamFailureError(IdentityError):
    """An upstream returned a rejected request or malformed/oversized response."""


class AvatarMissingError(IdentityError):
    """The authenticated user has no supported avatar."""


@unique
class ImageType(StrEnum):
    """Supported non-active avatar media types."""

    JPEG = "image/jpeg"
    PNG = "image/png"


def safe_return_path(value: str) -> str:
    """Return a safe origin-relative path unchanged, including its encoding.

    Raise ``InvalidCallbackError`` when the path is unsafe, ambiguous or not
    origin-relative.
    """
    decoded = unquote(value)
    origin_relative = value.startswith("/") and not decoded.startswith("//")
    ambiguous = "\\" in decoded or "%" in decoded or not decoded.isprintable()
    # Parse last and lazily: urlsplit can raise on input rejected above.
    if not origin_relative or ambiguous or urlsplit(decoded).scheme:
        raise InvalidCallbackError
    return value


def canonical_uuid(value: str) -> str:
    """Return ``value`` as a canonical lowercase UUID; raise ``ValueError`` otherwise.

    The error chain contains neither the input nor raw parser diagnostics.
    """
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        message = "Invalid identity identifier."
    # Raise after leaving the handler so raw input cannot survive as error context.
    raise ValueError(message)


def _canonical_origin(*, origin: str, allow_insecure_loopback: bool) -> str:
    parsed: SplitResult | None = None
    hostname: str | None = None
    try:
        parsed = urlsplit(origin)
        hostname = parsed.hostname
    except ValueError:
        parsed = None
    if parsed is None:
        raise ValueError(_INVALID_ORIGIN_MESSAGE)
    secure = parsed.scheme == URLScheme.HTTPS
    local = (
        parsed.scheme == URLScheme.HTTP
        and allow_insecure_loopback
        and is_loopback_host(hostname)
    )
    allowed_scheme = secure or local
    # Short-circuit on the scheme first; the later checks assume text input.
    if (
        not allowed_scheme
        or not hostname
        or not _bare_origin(parsed=parsed, origin=origin)
        or not _plain_origin_text(origin)
    ):
        raise ValueError(_INVALID_ORIGIN_MESSAGE)
    # Reject malformed ports without including configuration values in errors.
    port = _origin_port(parsed)
    host = _canonical_origin_host(hostname)
    # Checked last so origins rejected by an earlier check keep their message.
    if port == 0 or not _hostname_or_ipv6_literal(parsed):
        raise ValueError(_INVALID_ORIGIN_MESSAGE)
    default = _DEFAULT_HTTPS_PORT if secure else _DEFAULT_HTTP_PORT
    authority = host if port is None or port == default else f"{host}:{port}"
    return f"{parsed.scheme}://{authority}"


def _origin_port(parsed: SplitResult) -> int | None:
    try:
        return parsed.port
    except ValueError:
        message = _INVALID_ORIGIN_PORT_MESSAGE
    raise ValueError(message)


def _bare_origin(*, parsed: SplitResult, origin: str) -> bool:
    has_userinfo = parsed.username is not None or parsed.password is not None
    has_resource = bool(parsed.path or parsed.query or parsed.fragment)
    round_trips = origin == f"{parsed.scheme}://{parsed.netloc}"
    return not has_userinfo and not has_resource and round_trips


def _plain_origin_text(origin: str) -> bool:
    printable_ascii = origin.isascii() and origin.isprintable()
    has_whitespace = any(character.isspace() for character in origin)
    has_ambiguous_character = "\\" in origin or "%" in origin
    return printable_ascii and not has_whitespace and not has_ambiguous_character


def _hostname_or_ipv6_literal(parsed: SplitResult) -> bool:
    # RFC 1123 hostnames use letters, digits, hyphens and dot separators; brackets
    # are reserved for IPv6 literals, so IPvFuture forms are not origins here.
    host = parsed.hostname or ""
    if not parsed.netloc.startswith("["):
        hostname_length = len(host.removesuffix("."))
        return (
            hostname_length <= _MAX_HOSTNAME_LENGTH
            and _HOSTNAME_TEXT.fullmatch(host) is not None
        )
    try:
        return isinstance(ipaddress.ip_address(host), ipaddress.IPv6Address)
    except ValueError:
        return False


def _canonical_origin_host(host: str) -> str:
    try:
        address = ipaddress.ip_address(host.rstrip("."))
    except ValueError:
        # Browsers interpret numeric final labels as IPv4, including shorthand
        # forms that urllib does not normalize. Reject those ambiguous aliases.
        if _NUMERIC_HOST_LABEL.fullmatch(host.rstrip(".").split(".")[-1]):
            message = "Invalid identity origin host."
            raise ValueError(message) from None
        return host.lower()
    return (
        f"[{address}]" if isinstance(address, ipaddress.IPv6Address) else str(address)
    )


def _validate_ttl(value: int, maximum: int) -> None:
    if not is_int_in_range(value, low=1, high=maximum):
        message = "Invalid identity TTL."
        raise ValueError(message)


@dataclass(frozen=True, kw_only=True, slots=True)
class IdentityConfig:
    """Explicit Entra v2 settings; construction raises ``ValueError`` if unsafe.

    ``tenant_id`` and ``client_id`` are canonical UUIDs; ``api_audience`` is the
    exact API registration audience. ``origin`` is a fixed origin without a path
    or trailing slash, normalized to lowercase host and without a default port,
    never taken from a request; its host is an RFC 1123 name or bracketed IPv6
    literal and its port is never 0. ``allow_insecure_loopback``
    permits HTTP cookies only on literal loopback hosts. TTLs are positive,
    bounded seconds; session expiry is absolute, not sliding.

    Attributes:
        tenant_id (str): Canonical Entra tenant UUID.
        client_id (str): Canonical confidential-client UUID.
        api_audience (str): Exact, nonempty printable API audience.
        origin (str): Fixed HTTPS browser origin, normalized at construction.
        allow_insecure_loopback (bool): Explicitly permit HTTP on literal loopback.
        session_ttl_seconds (int): Absolute session lifetime in (0, 86400].
        cache_ttl_seconds (int): Private profile/photo cache lifetime in (0, 900].
    """

    tenant_id: str
    client_id: str
    api_audience: str
    origin: str
    allow_insecure_loopback: bool = False
    session_ttl_seconds: int = _SESSION_TTL_SECONDS
    cache_ttl_seconds: int = CACHE_TTL_SECONDS

    def __post_init__(self) -> None:
        """Validate identifiers, the fixed origin and bounded positive TTLs.

        Raises:
            ValueError: Identifiers, audience, origin, development flag or TTLs are unsafe.
        """
        if type(self.allow_insecure_loopback) is not bool:
            message = "Identity allow_insecure_loopback must be an explicit boolean."
            raise ValueError(message)
        for value in (self.tenant_id, self.client_id):
            if canonical_uuid(value) != value:
                message = "Identity identifiers must be canonical UUIDs."
                raise ValueError(message)
        if not self.api_audience or not self.api_audience.isprintable():
            message = "Invalid identity api_audience."
            raise ValueError(message)
        object.__setattr__(
            self,
            "origin",
            _canonical_origin(
                origin=self.origin,
                allow_insecure_loopback=self.allow_insecure_loopback,
            ),
        )
        _validate_ttl(self.session_ttl_seconds, _MAX_SESSION_TTL_SECONDS)
        _validate_ttl(self.cache_ttl_seconds, _MAX_CACHE_TTL_SECONDS)

    @property
    def authority(self) -> str:
        """The fixed HTTPS Entra authority for the configured tenant."""
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @property
    def issuer(self) -> str:
        """The only accepted v2 token issuer."""
        return f"{self.authority}/v2.0"

    @property
    def redirect_uri(self) -> str:
        """The fixed callback URL, independent of proxy headers."""
        return f"{self.origin}/auth/callback"

    @property
    def secure_cookies(self) -> bool:
        """Whether cookies require HTTPS because the origin uses it."""
        return urlsplit(self.origin).scheme == URLScheme.HTTPS


@dataclass(frozen=True, kw_only=True, slots=True)
class Principal:
    """Safe identity identifiers and verified authorization claims.

    Attributes:
        tenant_id (str): Verified tenant UUID.
        subject_id (str): Verified user object UUID.
        scopes (frozenset[str]): Verified delegated scopes.
        roles (frozenset[str]): Verified application roles.
    """

    tenant_id: str
    subject_id: str
    scopes: frozenset[str] = frozenset()
    roles: frozenset[str] = frozenset()

    def require(self, *, scopes: frozenset[str], roles: frozenset[str]) -> None:
        """Require all ``scopes`` and ``roles``.

        Args:
            scopes (frozenset[str]): Every delegated scope required by the caller.
            roles (frozenset[str]): Every application role required by the caller.

        Raises:
            ValueError: Neither permission set is specified.
            PermissionDeniedError: Any required permission is absent.
        """
        if not scopes and not roles:
            message = "Explicit identity permissions are required."
            raise ValueError(message)
        if not scopes <= self.scopes or not roles <= self.roles:
            raise PermissionDeniedError


@dataclass(frozen=True, kw_only=True, slots=True)
class ProviderLogin:
    """Authorization URL and server-only serialized SDK login flow.

    Attributes:
        authorization_url (str): Provider redirect target; omitted from repr.
        flow (str): Private serialized PKCE/state/nonce flow; omitted from repr.
    """

    authorization_url: str = field(repr=False)
    flow: str = field(repr=False)


@dataclass(frozen=True, kw_only=True, slots=True)
class ProviderTokens:
    """Server-only delegated Graph token and serialized SDK token cache.

    Attributes:
        principal (Principal): Independently verified identity and permissions.
        access_token (str): Private delegated Graph token; omitted from repr.
        cache (str): Private serialized SDK token cache; omitted from repr.
        expires_at (float): Access-token expiry as Unix time in seconds.
    """

    principal: Principal
    access_token: str = field(repr=False)
    cache: str = field(repr=False)
    expires_at: float


@dataclass(frozen=True, kw_only=True, slots=True)
class Login:
    """Browser redirect URL and opaque, HttpOnly browser-binding cookie.

    Attributes:
        authorization_url (str): Provider redirect target; omitted from repr.
        binding (str): Opaque browser binding; omitted from repr.
    """

    authorization_url: str = field(repr=False)
    binding: str = field(repr=False)


@dataclass(frozen=True, kw_only=True, slots=True)
class Authenticated:
    """New opaque session cookie and previously validated return path.

    Attributes:
        session_id (str): Opaque rotated session identifier; omitted from repr.
        return_to (str): Original validated origin-relative return path.
    """

    session_id: str = field(repr=False)
    return_to: str


@dataclass(frozen=True, kw_only=True, slots=True)
class Session:
    """Server-side session with absolute expiry and stable CSRF secret.

    Attributes:
        tokens (ProviderTokens): Private provider state; omitted from repr.
        csrf_token (str): Stable session-bound proof; omitted from repr.
        expires_at (float): Absolute session expiry as Unix time in seconds.
    """

    tokens: ProviderTokens = field(repr=False)
    csrf_token: str = field(repr=False)
    expires_at: float


@dataclass(frozen=True, kw_only=True, slots=True)
class SafeProfile:
    """Allowlisted display name; email and raw Graph data are not retained.

    Attributes:
        display_name (str | None): Validated display name, or no supplied name.
    """

    display_name: str | None


@dataclass(frozen=True, kw_only=True, slots=True)
class Avatar:
    """Bounded supported image bytes, never a URL or active content.

    Attributes:
        content (bytes): Nonempty image bytes within the size cap; omitted from repr.
        media_type (ImageType): Supported type matching the image signature.
    """

    content: bytes = field(repr=False)
    media_type: ImageType

    def __post_init__(self) -> None:
        """Check media type, byte signature and size.

        Raises:
            UpstreamFailureError: The type, byte signature or size is unsafe.
        """
        signatures = {
            ImageType.PNG: b"\x89PNG\r\n\x1a\n",
            ImageType.JPEG: b"\xff\xd8\xff",
        }
        if (
            self.media_type not in signatures
            or not 0 < len(self.content) <= MAX_AVATAR_BYTES
            or not self.content.startswith(signatures[self.media_type])
        ):
            raise UpstreamFailureError


def finite_number(value: object) -> float:
    """Return a finite ``int``/``float`` as ``float``; raise ``ValueError`` otherwise.

    Booleans and numeric subclasses are rejected.
    """
    if type(value) not in (int, float) or not isinstance(value, (int, float)):
        message = "Invalid identity numeric field."
        raise ValueError(message)
    if not math.isfinite(value):
        message = "Invalid identity numeric field."
        raise ValueError(message)
    return float(value)
