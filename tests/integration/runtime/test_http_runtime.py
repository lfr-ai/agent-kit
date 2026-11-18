import asyncio
from collections.abc import Iterator
import logging
from typing import Final

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind
from opentelemetry.util._once import Once
import pytest
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    BaseUser,
    SimpleUser,
)
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import HTTPConnection

from platform_kit_runtime import RuntimeConfig, create_app
from platform_kit_runtime.middleware import (
    ACCESS_LOGGER_NAME,
    REQUEST_ID_HEADER,
    RateLimitPolicy,
    RequestContextFilter,
    WindowCount,
)

pytestmark = pytest.mark.integration

PRIVATE_VALUE: Final[str] = "synthetic-secret-token"
TRACE_ID: Final[str] = "4bf92f3577b34da6a3ce929d0e0e4736"


class HeaderBackend(AuthenticationBackend):
    async def authenticate(
        self, conn: HTTPConnection
    ) -> tuple[AuthCredentials, BaseUser] | None:
        user = conn.headers.get("X-Test-User")
        return None if user is None else (AuthCredentials(), SimpleUser(user))


class CountingStore:
    def __init__(self) -> None:
        self.keys: list[str] = []

    async def hit(self, *, key: str, window_seconds: int) -> WindowCount:
        self.keys.append(key)
        return WindowCount(count=len(self.keys), reset_seconds=window_seconds)


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []
        self.addFilter(RequestContextFilter())

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def access_log() -> Iterator[ListHandler]:
    handler = ListHandler()
    logger = logging.getLogger(ACCESS_LOGGER_NAME)
    previous = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield handler
    logger.removeHandler(handler)
    logger.setLevel(previous)


@pytest.fixture
def exporter(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER_SET_ONCE", Once())
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", None)
    trace.set_tracer_provider(provider)
    yield exporter
    provider.shutdown()


def application(*, config: RuntimeConfig | None = None) -> FastAPI:
    app = create_app(config=config or RuntimeConfig(), probes=())

    @app.get("/items/{item_id}")
    async def item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError(PRIVATE_VALUE)

    return app


def send(*, app: FastAPI, requests: list[tuple[str, dict[str, str]]]) -> list[Response]:
    async def run() -> list[Response]:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://runtime.test",
        ) as client:
            return [
                await client.get(path, headers=headers) for path, headers in requests
            ]

    return asyncio.run(run())


def test_every_response_carries_a_request_id(access_log: ListHandler) -> None:
    app = application()

    responses = send(
        app=app,
        requests=[
            ("/health/live", {REQUEST_ID_HEADER: "client-1"}),
            ("/missing", {REQUEST_ID_HEADER: "x" * 129}),
            ("/boom", {REQUEST_ID_HEADER: "bad value"}),
        ],
    )

    assert [response.status_code for response in responses] == [200, 404, 500]
    ids = [response.headers[REQUEST_ID_HEADER] for response in responses]
    assert ids[0] == "client-1"
    assert ids[1] != "x" * 129
    assert ids[2] != "bad value"
    assert responses[2].headers["content-type"] == "application/problem+json"
    assert PRIVATE_VALUE not in responses[2].text
    assert [vars(record)["request_id"] for record in access_log.records] == ids
    assert [vars(record)["http_status"] for record in access_log.records] == [
        200,
        404,
        500,
    ]


def test_access_records_use_route_templates_and_no_request_data(
    access_log: ListHandler,
) -> None:
    app = application()

    send(
        app=app,
        requests=[
            (
                f"/items/7?token={PRIVATE_VALUE}",
                {"Authorization": f"Bearer {PRIVATE_VALUE}"},
            ),
            ("/health/ready", {}),
        ],
    )

    item, health = access_log.records
    assert item.levelno == logging.INFO
    assert vars(item)["http_route"] == "/items/{item_id}"
    assert vars(item)["http_method"] == "GET"
    assert vars(item)["trace_id"] is None
    assert PRIVATE_VALUE not in repr(vars(item))
    assert "/items/7" not in repr(vars(item))
    assert health.levelno == logging.DEBUG
    assert vars(health)["http_route"] == "/health/ready"


def test_rate_limit_through_the_factory_with_the_default_store() -> None:
    policy = RateLimitPolicy(limit=1, window_seconds=60)
    app = application(config=RuntimeConfig(rate_limit=policy))

    first, second, health = send(
        app=app,
        requests=[("/items/1", {}), ("/items/1", {}), ("/health/live", {})],
    )

    assert first.status_code == 200
    assert first.headers["RateLimit-Policy"] == '"default";q=1;w=60'
    assert first.headers["RateLimit"] == '"default";r=0;t=60'
    assert second.status_code == 429
    assert second.headers["content-type"] == "application/problem+json"
    assert int(second.headers["Retry-After"]) >= 1
    assert second.headers[REQUEST_ID_HEADER]
    assert second.json()["code"] == "rate_limited"
    assert health.status_code == 200
    assert "RateLimit" not in health.headers


def test_spoofed_forwarded_for_does_not_evade_the_limit() -> None:
    policy = RateLimitPolicy(limit=1, window_seconds=60)
    app = application(config=RuntimeConfig(rate_limit=policy))

    responses = send(
        app=app,
        requests=[
            ("/items/1", {"X-Forwarded-For": "198.51.100.1"}),
            ("/items/1", {"X-Forwarded-For": "198.51.100.2"}),
        ],
    )

    assert [response.status_code for response in responses] == [200, 429]


def test_trusted_proxy_hops_separate_forwarded_clients() -> None:
    policy = RateLimitPolicy(limit=1, window_seconds=60)
    app = application(config=RuntimeConfig(rate_limit=policy, trusted_proxy_hops=1))

    responses = send(
        app=app,
        requests=[
            ("/items/1", {"X-Forwarded-For": "6.6.6.6, 198.51.100.1"}),
            ("/items/1", {"X-Forwarded-For": "7.7.7.7, 198.51.100.2"}),
            ("/items/1", {"X-Forwarded-For": "8.8.8.8, 198.51.100.1"}),
        ],
    )

    assert [response.status_code for response in responses] == [200, 200, 429]


def test_later_authentication_middleware_keys_limits_by_principal() -> None:
    policy = RateLimitPolicy(limit=1, window_seconds=60)
    app = application(config=RuntimeConfig(rate_limit=policy))
    app.add_middleware(AuthenticationMiddleware, backend=HeaderBackend())

    responses = send(
        app=app,
        requests=[
            ("/items/1", {"X-Test-User": "alice"}),
            ("/items/1", {"X-Test-User": "bob"}),
            ("/items/1", {"X-Test-User": "alice"}),
        ],
    )

    assert [response.status_code for response in responses] == [200, 200, 429]


def test_a_caller_owned_store_is_shared_by_apps() -> None:
    store = CountingStore()
    config = RuntimeConfig(rate_limit=RateLimitPolicy(limit=2, window_seconds=30))
    first = create_app(config=config, probes=(), rate_limit_store=store)
    second = create_app(config=config, probes=(), rate_limit_store=store)

    responses = [
        *send(app=first, requests=[("/missing", {}), ("/missing", {})]),
        *send(app=second, requests=[("/missing", {})]),
    ]

    assert [response.status_code for response in responses] == [404, 404, 429]
    assert len(store.keys) == 3


def test_tracing_records_server_spans_except_health(
    exporter: InMemorySpanExporter, access_log: ListHandler
) -> None:
    app = application(config=RuntimeConfig(tracing=True))
    parent = {"traceparent": f"00-{TRACE_ID}-00f067aa0ba902b7-01"}

    send(
        app=app,
        requests=[
            (f"/items/7?token={PRIVATE_VALUE}", parent),
            ("/health/live", parent),
        ],
    )

    servers = [
        span for span in exporter.get_finished_spans() if span.kind is SpanKind.SERVER
    ]
    [server] = servers
    attributes = server.attributes or {}
    assert attributes["http.route"] == "/items/{item_id}"
    assert attributes["http.response.status_code"] == 200
    assert f"{server.context.trace_id:032x}" == TRACE_ID
    item, health = access_log.records
    assert vars(item)["trace_id"] == TRACE_ID
    assert vars(health)["trace_id"] is None


def test_tracing_off_records_no_spans_even_with_a_global_provider(
    exporter: InMemorySpanExporter,
) -> None:
    send(app=application(), requests=[("/items/7", {})])

    assert not exporter.get_finished_spans()
