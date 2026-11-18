"""Pure ASGI request correlation and access logging around the error boundary."""

from enum import StrEnum, auto, unique
from http import HTTPMethod, HTTPStatus
import logging
import time
from typing import Final

from fastapi import FastAPI
from starlette.datastructures import Headers, MutableHeaders
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from platform_kit_runtime.core.correlation import (
    REQUEST_ID_HEADER,
    bound_request_id,
    current_request_id,
    resolve_request_id,
)
from platform_kit_runtime.core.limits import MILLISECONDS_PER_SECOND

ACCESS_LOGGER_NAME: Final[str] = "platform_kit_runtime.access"
HEALTH_PATHS: Final[frozenset[str]] = frozenset({"/health/live", "/health/ready"})
HTTP_RESPONSE_START: Final[str] = "http.response.start"

_ACCESS_LOGGER = logging.getLogger(ACCESS_LOGGER_NAME)
_DURATION_DIGITS = 3
# OpenTelemetry's placeholder for methods outside the known set.
_OTHER_METHOD = "_OTHER"


@unique
class ScopeType(StrEnum):
    """ASGI connection scope types the runtime middleware acts on."""

    HTTP = auto()
    WEBSOCKET = auto()


def is_health_request(scope: Scope) -> bool:
    """Return whether ``scope`` targets ``/health/live`` or ``/health/ready``."""
    path: str = scope.get("path", "")
    root_path: str = scope.get("root_path", "")
    return path.removeprefix(root_path) in HEALTH_PATHS


class RequestCorrelationMiddleware:
    """Bind a request ID for each HTTP or WebSocket scope; echo it on responses.

    One valid inbound ``X-Request-ID`` is kept; missing, repeated, oversized or
    malformed values are replaced with a UUID4, never echoed or logged.
    """

    def __init__(self, app: ASGIApp, /) -> None:
        """Wrap ``app``; positional to match the ASGI middleware factory shape.

        Args:
            app (ASGIApp): Inner application.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the inner app with the request ID bound in a context variable.

        Args:
            scope (Scope): ASGI connection scope.
            receive (Receive): ASGI receive channel.
            send (Send): ASGI send channel.
        """
        if scope["type"] not in ScopeType:
            await self.app(scope, receive, send)
            return
        request_id = resolve_request_id(
            values=Headers(scope=scope).getlist(REQUEST_ID_HEADER)
        )

        async def send_with_id(message: Message) -> None:
            if message["type"] == HTTP_RESPONSE_START:
                message.setdefault("headers", [])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        with bound_request_id(request_id=request_id):
            await self.app(scope, receive, send_with_id)


class AccessLogMiddleware:
    """Emit one structured record per HTTP request on ``platform_kit_runtime.access``.

    Records hold the method, route template, status, duration and request ID.
    Raw paths, query strings, headers, bodies and client addresses are never
    logged. Health routes log at ``DEBUG``, other requests at ``INFO``.
    Cancelled requests are not logged.
    """

    def __init__(self, app: ASGIApp, /) -> None:
        """Wrap ``app``; positional to match the ASGI middleware factory shape.

        Args:
            app (ASGIApp): Inner application.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the inner app, then log its outcome; exceptions propagate.

        Args:
            scope (Scope): ASGI connection scope.
            receive (Receive): ASGI receive channel.
            send (Send): ASGI send channel.
        """
        if scope["type"] != ScopeType.HTTP:
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        # A server answers 500 when the app fails before starting a response.
        status = HTTPStatus.INTERNAL_SERVER_ERROR.value

        async def send_with_status(message: Message) -> None:
            nonlocal status
            if message["type"] == HTTP_RESPONSE_START:
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        except Exception:
            _log_access(scope=scope, status=status, started=started)
            raise
        _log_access(scope=scope, status=status, started=started)


class RuntimeFastAPI(FastAPI):
    """FastAPI whose correlation and access log wrap its error boundary."""

    def build_middleware_stack(self) -> ASGIApp:
        """Wrap FastAPI's stack so even generic 500 responses are correlated."""
        return RequestCorrelationMiddleware(
            AccessLogMiddleware(super().build_middleware_stack())
        )


def _route_template(scope: Scope) -> str | None:
    route = scope.get("route")
    return route.path_format if isinstance(route, (Route, Mount)) else None


def _log_access(*, scope: Scope, status: int, started: float) -> None:
    method: str = scope["method"]
    duration = (time.perf_counter() - started) * MILLISECONDS_PER_SECOND
    _ACCESS_LOGGER.log(
        logging.DEBUG if is_health_request(scope) else logging.INFO,
        "HTTP request completed",
        extra={
            "event": "runtime.http_request",
            "http_method": method if method in HTTPMethod else _OTHER_METHOD,
            "http_route": _route_template(scope),
            "http_status": status,
            "duration_ms": round(duration, _DURATION_DIGITS),
            "request_id": current_request_id(),
        },
    )
