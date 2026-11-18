"""Public opt-in identity facade/composition root; importing it loads no SDKs."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI

from platform_kit_runtime.application.identity import IdentityService
from platform_kit_runtime.core.identity.models import (
    AuthenticationRequiredError,
    Avatar,
    AvatarMissingError,
    DependencyUnavailableError,
    IdentityConfig,
    IdentityError,
    ImageType,
    InvalidCallbackError,
    PermissionDeniedError,
    Principal,
    ProviderLogin,
    ProviderTokens,
    SafeProfile,
    UpstreamFailureError,
)
from platform_kit_runtime.core.identity.ports import (
    BearerValidator,
    ClientAssertion,
    GraphReader,
    IdentityProvider,
    IdentityStore,
)
from platform_kit_runtime.core.validation import (
    URLScheme,
    has_query_or_fragment,
    is_loopback_host,
)
from platform_kit_runtime.presentation.identity.problems import (
    ensure_identity_handlers,
    install_identity_handlers,
)
from platform_kit_runtime.presentation.identity.routes import IdentityRoutes
from platform_kit_runtime.presentation.identity.security import (
    BearerGuard,
    SessionGuard,
)

if TYPE_CHECKING:
    import httpx

__all__: Final[list[str]] = [
    "AuthenticationRequiredError",
    "Avatar",
    "AvatarMissingError",
    "BearerGuard",
    "BearerValidator",
    "ClientAssertion",
    "DependencyUnavailableError",
    "GraphReader",
    "IdentityConfig",
    "IdentityError",
    "IdentityProvider",
    "IdentityRuntime",
    "IdentityStore",
    "ImageType",
    "InvalidCallbackError",
    "PermissionDeniedError",
    "Principal",
    "ProviderLogin",
    "ProviderTokens",
    "SafeProfile",
    "SessionGuard",
    "UpstreamFailureError",
    "create_identity",
    "install_identity_handlers",
    "open_entra_bearer",
    "open_entra_identity",
]

_HTTP_TIMEOUT_SECONDS = 10
_MAX_HTTP_CONNECTIONS = 32
_MAX_REDIS_CONNECTIONS = 32


def _bounded_http_client[ClientT: (httpx.Client, httpx.AsyncClient)](
    client_type: type[ClientT],
) -> ClientT:
    """Construct a bounded HTTPX client without redirects or ambient settings."""
    import httpx  # noqa: PLC0415 - optional SDKs load only when a lifespan is entered

    return client_type(
        timeout=_HTTP_TIMEOUT_SECONDS,
        follow_redirects=False,
        trust_env=False,
        limits=httpx.Limits(max_connections=_MAX_HTTP_CONNECTIONS),
    )


@dataclass(frozen=True, kw_only=True, slots=True)
class IdentityRuntime:
    """Isolated identity bundle; owns no resources.

    Attributes:
        config (IdentityConfig): Fixed trust boundaries and TTL policy.
        service (IdentityService): Browser use cases over caller-owned ports.
        validator (BearerValidator): API token signature and claim validator.
    """

    config: IdentityConfig
    service: IdentityService
    validator: BearerValidator

    def router(self) -> APIRouter:
        """Return a fresh BFF router; pre-register handlers on its owning app.

        The router's lifespan raises ``RuntimeError`` when startup finds missing
        identity handlers. Handler registration itself must happen before startup.
        """
        return IdentityRoutes(config=self.config, service=self.service).router()

    def install(self, *, app: FastAPI) -> None:
        """Install BFF routes once, registering handlers when called before startup.

        When resources are created inside lifespan, call
        ``install_identity_handlers(app=app)`` before startup, then call this
        method inside lifespan to attach the resource-backed routes. If the
        middleware was built without pre-registered identity handlers, the
        ``RuntimeError`` propagates.
        """
        ensure_identity_handlers(app=app)
        app.include_router(self.router())


def create_identity(
    *,
    config: IdentityConfig,
    store: IdentityStore,
    provider: IdentityProvider,
    graph: GraphReader,
    validator: BearerValidator,
) -> IdentityRuntime:
    """Compose explicit ports into a resource-free runtime without network I/O.

    ``config`` sets fixed trust boundaries; ``store`` is private and atomic;
    ``provider`` performs OIDC, ``graph`` reads safe profile data, and
    ``validator`` verifies API tokens. The caller owns each port's lifecycle.

    Args:
        config (IdentityConfig): Fixed trust boundaries and TTL policy.
        store (IdentityStore): Private atomic TTL store.
        provider (IdentityProvider): OIDC flow and refresh adapter.
        graph (GraphReader): Safe delegated profile/photo reader.
        validator (BearerValidator): API token signature and claim validator.

    Returns:
        IdentityRuntime: Independent service bundle using the supplied ports.
    """
    return IdentityRuntime(
        config=config,
        validator=validator,
        service=IdentityService(
            config=config, store=store, provider=provider, graph=graph
        ),
    )


@asynccontextmanager
async def open_entra_bearer(
    *, config: IdentityConfig
) -> AsyncGenerator[BearerValidator]:
    """Own an HTTPX/JWT validator lifespan without Redis or MSAL.

    Entering it raises ``ImportError`` when the optional HTTPX/PyJWT dependencies
    are not installed. It yields a signature-verifying ``BearerValidator`` for
    ``BearerGuard``.
    """
    import httpx  # noqa: PLC0415 - optional SDKs load only when this lifespan is entered

    from platform_kit_runtime.infrastructure.identity.http import HttpxIdentityTransport  # noqa: PLC0415 - opt-in composition
    from platform_kit_runtime.infrastructure.identity.jwt import EntraJWTValidator  # noqa: PLC0415 - opt-in composition

    async with _bounded_http_client(httpx.AsyncClient) as client:
        yield EntraJWTValidator(
            config=config, http=HttpxIdentityTransport(client=client)
        )


def _validate_redis_url(*, redis_url: str, config: IdentityConfig) -> None:
    try:
        parsed = urlsplit(redis_url)
        _ = parsed.port
    except ValueError as error:
        message = "Invalid identity Redis URL."
        raise ValueError(message) from error
    secure = parsed.scheme == URLScheme.REDISS
    local = (
        parsed.scheme == URLScheme.REDIS
        and config.allow_insecure_loopback
        and is_loopback_host(parsed.hostname)
    )
    # The text checks stay last and lazy: they assume a str URL, which the
    # scheme comparison above already guarantees.
    if (
        not parsed.hostname
        or not (secure or local)
        or has_query_or_fragment(redis_url)
        or not redis_url.isprintable()
    ):
        message = "Identity Redis requires TLS or explicit loopback development mode."
        raise ValueError(message)


@asynccontextmanager
async def open_entra_identity(
    *,
    config: IdentityConfig,
    redis_url: str,
    assertion: ClientAssertion,
) -> AsyncGenerator[IdentityRuntime]:
    """Own the BFF adapters and close Redis/HTTPX clients on lifespan exit.

    No connections are opened until a request. MSAL runs in worker threads;
    client assertions are supplied by the consumer's workload/certificate flow.
    Entering it raises ``ValueError`` for unsafe Redis transport configuration
    and ``ImportError`` when optional MSAL/PyJWT/Redis/HTTPX dependencies are
    absent.

    Args:
        config (IdentityConfig): Explicit trust boundaries and bounded TTLs.
        redis_url (str): Private Redis 6.2+ endpoint; TLS is mandatory outside loopback.
        assertion (ClientAssertion): Short-lived confidential-client assertion supplier.

    Yields:
        IdentityRuntime: Install its router before the application starts serving.
    """
    _validate_redis_url(redis_url=redis_url, config=config)
    import httpx  # noqa: PLC0415 - optional SDKs load only when this lifespan is entered
    from redis.asyncio import Redis  # noqa: PLC0415 - opt-in composition

    from platform_kit_runtime.infrastructure.identity.graph import GraphAdapter  # noqa: PLC0415 - opt-in composition
    from platform_kit_runtime.infrastructure.identity.http import HttpxIdentityTransport  # noqa: PLC0415 - opt-in composition
    from platform_kit_runtime.infrastructure.identity.jwt import EntraJWTValidator  # noqa: PLC0415 - opt-in composition
    from platform_kit_runtime.infrastructure.identity.msal import EntraIdentityProvider  # noqa: PLC0415 - opt-in composition
    from platform_kit_runtime.infrastructure.identity.msal_http import MSALHTTPTransport  # noqa: PLC0415 - opt-in composition
    from platform_kit_runtime.infrastructure.identity.redis import RedisIdentityStore  # noqa: PLC0415 - opt-in composition

    async with (
        Redis.from_url(
            redis_url,
            decode_responses=False,
            socket_timeout=_HTTP_TIMEOUT_SECONDS,
            socket_connect_timeout=_HTTP_TIMEOUT_SECONDS,
            max_connections=_MAX_REDIS_CONNECTIONS,
        ) as redis_client,
        _bounded_http_client(httpx.AsyncClient) as http_client,
    ):
        with _bounded_http_client(httpx.Client) as sync_client:
            http = HttpxIdentityTransport(client=http_client)
            validator = EntraJWTValidator(config=config, http=http)
            yield create_identity(
                config=config,
                validator=validator,
                store=RedisIdentityStore(client=redis_client),
                graph=GraphAdapter(http=http),
                provider=EntraIdentityProvider(
                    config=config,
                    validator=validator,
                    http=MSALHTTPTransport(client=sync_client),
                    assertion=assertion,
                ),
            )
