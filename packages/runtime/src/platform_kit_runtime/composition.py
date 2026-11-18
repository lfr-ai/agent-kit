"""Compose the base ASGI app without ambient applications or resources."""

import logging

from fastapi import FastAPI
from fastapi.telemetry import TelemetryConfig
from starlette.types import Lifespan

from platform_kit_runtime.application.rate_limit import RateLimitService
from platform_kit_runtime.application.readiness import ReadinessService
from platform_kit_runtime.config import RuntimeConfig
from platform_kit_runtime.core.rate_limit import RateLimitStore
from platform_kit_runtime.core.readiness import ReadinessProbe
from platform_kit_runtime.infrastructure.rate_limit.memory import InMemoryRateLimitStore
from platform_kit_runtime.infrastructure.telemetry import tracing_available
from platform_kit_runtime.presentation.health import install_health_routes
from platform_kit_runtime.presentation.middleware import (
    RuntimeFastAPI,
    is_health_request,
)
from platform_kit_runtime.presentation.problems import install_problem_handlers
from platform_kit_runtime.presentation.rate_limit import RateLimitMiddleware

_LOGGER = logging.getLogger(__name__)


def create_app(
    *,
    config: RuntimeConfig,
    probes: tuple[ReadinessProbe, ...],
    lifespan: Lifespan[FastAPI] | None = None,
    rate_limit_store: RateLimitStore | None = None,
) -> FastAPI:
    """Create an independent ASGI application with health routes and safe errors.

    Every app correlates requests and writes one access record per request.
    From outermost to innermost, a request passes FastAPI's server span when
    tracing is on, request correlation, access logging, the 500 boundary,
    middleware the caller adds later, rate limiting when configured, the
    problem handlers and the router. Later middleware therefore runs before
    rate limiting and can authenticate the principal it is keyed by.

    Args:
        config (RuntimeConfig): Explicit validated settings; no environment,
            dotenv, file discovery, or global defaults are consulted. With
            ``tracing``, standard ``OTEL_*`` variables configure span export.
        probes (tuple[ReadinessProbe, ...]): Consumer-owned async checks, shared
            across requests to this app only. Explicit ``()`` means no required
            dependencies. The caller owns resource initialization and teardown.
        lifespan (Lifespan[FastAPI] | None): Optional consumer-owned async
            context manager, passed directly to FastAPI. Startup and shutdown
            failures propagate; this factory never enters the context itself.
        rate_limit_store (RateLimitStore | None): Caller-owned counter store
            shared by replicas. ``None`` keeps counts in this app's memory, so
            each replica enforces ``config.rate_limit`` separately.

    Returns:
        FastAPI: A new app with ``/health/live`` and ``/health/ready``. Interactive
            docs, OpenAPI routes, debug responses, and slash redirects are off.
            Probes run only on readiness requests, not during construction.

    Raises:
        ValueError: ``rate_limit_store`` is given without ``config.rate_limit``.
    """
    if rate_limit_store is not None and config.rate_limit is None:
        message = "rate_limit_store requires config.rate_limit."
        raise ValueError(message)
    readiness = ReadinessService(
        probes=probes, timeout_seconds=config.readiness_timeout_seconds
    )
    app = RuntimeFastAPI(
        title="Platform Kit Runtime",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
        lifespan=lifespan,
        telemetry=_telemetry(tracing=config.tracing),
    )
    install_problem_handlers(app=app)
    install_health_routes(app=app, readiness=readiness)
    if config.rate_limit is not None:
        store = (
            InMemoryRateLimitStore() if rate_limit_store is None else rate_limit_store
        )
        app.add_middleware(
            RateLimitMiddleware,
            limiter=RateLimitService(policy=config.rate_limit, store=store),
            trusted_proxy_hops=config.trusted_proxy_hops,
        )
    return app


def _telemetry(*, tracing: bool) -> TelemetryConfig:
    """Select FastAPI's native tracing; metrics and exception logs stay off."""
    if tracing and tracing_available():
        return {
            "metrics": False,
            "logs": False,
            "auto_configure": True,
            "exclude": is_health_request,
        }
    if tracing:
        _LOGGER.warning(
            "Tracing disabled; the telemetry extra is not installed",
            extra={"event": "runtime.telemetry_unavailable"},
        )
    # Explicit, because FastAPI traces whenever a global SDK provider exists.
    return {"tracing": False, "metrics": False, "logs": False}
