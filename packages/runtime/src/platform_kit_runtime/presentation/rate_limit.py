"""Opt-in pure ASGI rate limiting with RFC 9457 429 responses and quota headers."""

from collections.abc import Mapping
from http import HTTPStatus
import ipaddress

from starlette.authentication import BaseUser
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from platform_kit_runtime.application.rate_limit import RateLimitService
from platform_kit_runtime.core.rate_limit import RateLimitDecision
from platform_kit_runtime.presentation.middleware import (
    HTTP_RESPONSE_START,
    ScopeType,
    is_health_request,
)
from platform_kit_runtime.presentation.problems import ProblemCode, problem_response

_FORWARDED_FOR = "X-Forwarded-For"
_POLICY_NAME = '"default"'
_UNKNOWN_CLIENT = "unknown"


class RateLimitMiddleware:
    """Count HTTP requests per client before routing; health routes are exempt.

    Clients are keyed by ``scope["user"].identity`` when an authentication
    middleware placed an authenticated Starlette user there, otherwise by IP.
    ``X-Forwarded-For`` is read only for configured trusted proxy hops. Allowed
    responses carry ``RateLimit-Policy`` and ``RateLimit``; rejected requests get
    a 429 problem with ``Retry-After``. A failed store lets requests through.
    """

    def __init__(
        self, app: ASGIApp, /, *, limiter: RateLimitService, trusted_proxy_hops: int
    ) -> None:
        """Wrap ``app``; positional to match the ASGI middleware factory shape.

        Args:
            app (ASGIApp): Inner application.
            limiter (RateLimitService): Policy and store applied to each request.
            trusted_proxy_hops (int): Reverse proxies that append to
                ``X-Forwarded-For``; ``0`` uses only the connection's peer address.
        """
        self.app = app
        self._limiter = limiter
        self._trusted_proxy_hops = trusted_proxy_hops

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject an over-limit request or run the inner app with quota headers.

        Args:
            scope (Scope): ASGI connection scope.
            receive (Receive): ASGI receive channel.
            send (Send): ASGI send channel.
        """
        if scope["type"] != ScopeType.HTTP or is_health_request(scope):
            await self.app(scope, receive, send)
            return
        key = _principal_key(scope) or _address_key(
            scope, trusted_proxy_hops=self._trusted_proxy_hops
        )
        decision = await self._limiter.check(key=key)
        if decision is None:
            await self.app(scope, receive, send)
            return
        headers = _quota_headers(decision=decision)
        if not decision.allowed:
            rejection = problem_response(
                status=HTTPStatus.TOO_MANY_REQUESTS,
                code=ProblemCode.RATE_LIMITED,
                headers={**headers, "Retry-After": str(decision.reset_seconds)},
            )
            await rejection(scope, receive, send)
            return
        await self.app(scope, receive, _send_with_headers(send=send, headers=headers))


def _send_with_headers(*, send: Send, headers: Mapping[str, str]) -> Send:
    async def send_with_headers(message: Message) -> None:
        if message["type"] == HTTP_RESPONSE_START:
            message.setdefault("headers", [])
            response_headers = MutableHeaders(scope=message)
            for name, value in headers.items():
                response_headers[name] = value
        await send(message)

    return send_with_headers


def _principal_key(scope: Scope) -> str | None:
    user = scope.get("user")
    if not isinstance(user, BaseUser):
        return None
    try:
        identity = user.identity if user.is_authenticated else ""
    except NotImplementedError:
        return None
    return f"principal:{identity}" if identity else None


def _address_key(scope: Scope, *, trusted_proxy_hops: int) -> str:
    forwarded = [
        entry
        for value in Headers(scope=scope).getlist(_FORWARDED_FOR)
        for entry in value.split(",")
    ]
    if trusted_proxy_hops and len(forwarded) >= trusted_proxy_hops:
        address = _ip_address(value=forwarded[-trusted_proxy_hops])
        if address is not None:
            return f"address:{address}"
    client: tuple[str, int] | None = scope.get("client")
    return f"address:{client[0] if client else _UNKNOWN_CLIENT}"


def _ip_address(*, value: str) -> str | None:
    candidate = value.strip()
    if candidate.startswith("["):
        candidate = candidate.removeprefix("[").partition("]")[0]
    elif candidate.count(":") == 1:
        candidate = candidate.partition(":")[0]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _quota_headers(*, decision: RateLimitDecision) -> Mapping[str, str]:
    return {
        "RateLimit-Policy": (
            f"{_POLICY_NAME};q={decision.limit};w={decision.window_seconds}"
        ),
        "RateLimit": f"{_POLICY_NAME};r={decision.remaining};t={decision.reset_seconds}",
    }
