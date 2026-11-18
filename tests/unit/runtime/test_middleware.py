import asyncio
import logging

import pytest
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from platform_kit_runtime.core.correlation import (
    MAX_REQUEST_ID_LENGTH,
    REQUEST_ID_HEADER,
    bound_request_id,
    current_request_id,
    resolve_request_id,
)
from platform_kit_runtime.middleware import ACCESS_LOGGER_NAME
from platform_kit_runtime.presentation.middleware import (
    AccessLogMiddleware,
    RequestCorrelationMiddleware,
    is_health_request,
)

pytestmark = pytest.mark.unit

_PRIVATE = "synthetic-secret-value"


def http_scope(
    *,
    path: str = "/items/7",
    method: str = "GET",
    headers: tuple[tuple[str, str], ...] = (),
    root_path: str = "",
) -> Scope:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "root_path": root_path,
        "query_string": f"token={_PRIVATE}".encode(),
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in headers
        ],
        "client": ("203.0.113.9", 4321),
    }


def call(app: ASGIApp, scope: Scope) -> list[Message]:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    async def run() -> None:
        await app(scope, receive, send)

    asyncio.run(run())
    return sent


def responding(
    *,
    status: int = 200,
    headers: list[tuple[bytes, bytes]] | None = None,
    seen: list[str | None] | None = None,
) -> ASGIApp:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if seen is not None:
            seen.append(current_request_id())
        start: Message = {"type": "http.response.start", "status": status}
        if headers is not None:
            start["headers"] = headers
        await send(start)
        await send({"type": "http.response.body", "body": b"ok"})

    return app


def response_headers(messages: list[Message]) -> list[tuple[bytes, bytes]]:
    return messages[0]["headers"]


@pytest.mark.parametrize(
    "value",
    [
        "a",
        "0f8c6d1e-7b1a-4c57-9a1e-5b2c3d4e5f60",
        "trace:abc.DEF_123+/=-",
        "x" * MAX_REQUEST_ID_LENGTH,
    ],
)
def test_one_valid_inbound_request_id_is_kept(value: str) -> None:
    assert resolve_request_id(values=[value]) == value


@pytest.mark.parametrize(
    "values",
    [
        [],
        [""],
        ["x" * (MAX_REQUEST_ID_LENGTH + 1)],
        ["has space"],
        ["line\nbreak"],
        ["<script>"],
        ['quote"d'],
        ["caf\u00e9"],
        ["one", "two"],
        ["same", "same"],
    ],
)
def test_missing_invalid_or_repeated_request_ids_are_replaced(
    values: list[str],
) -> None:
    resolved = resolve_request_id(values=values)

    assert resolved not in values
    assert len(resolved) == len("00000000-0000-4000-8000-000000000000")


def test_generated_request_ids_are_unique() -> None:
    assert resolve_request_id(values=[]) != resolve_request_id(values=[])


def test_bound_request_id_is_scoped_and_restored() -> None:
    assert current_request_id() is None
    with bound_request_id(request_id="outer"):
        with bound_request_id(request_id="inner"):
            assert current_request_id() == "inner"
        assert current_request_id() == "outer"
    assert current_request_id() is None


def test_bound_request_id_is_restored_after_an_error() -> None:
    with pytest.raises(LookupError), bound_request_id(request_id="failing"):
        raise LookupError
    assert current_request_id() is None


def test_correlation_binds_and_echoes_a_valid_inbound_id() -> None:
    seen: list[str | None] = []
    app = RequestCorrelationMiddleware(responding(seen=seen))

    messages = call(app, http_scope(headers=((REQUEST_ID_HEADER, "client-id-1"),)))

    assert seen == ["client-id-1"]
    assert response_headers(messages) == [(b"x-request-id", b"client-id-1")]
    assert messages[1]["body"] == b"ok"
    assert current_request_id() is None


def test_correlation_replaces_an_invalid_id_and_inner_app_values() -> None:
    seen: list[str | None] = []
    inner = responding(
        seen=seen,
        headers=[(b"x-request-id", b"inner"), (b"content-type", b"text/plain")],
    )
    app = RequestCorrelationMiddleware(inner)

    messages = call(app, http_scope(headers=((REQUEST_ID_HEADER, "bad id\t"),)))

    generated = seen[0]
    assert generated is not None
    assert generated != "bad id\t"
    headers = response_headers(messages)
    assert headers.count((b"x-request-id", generated.encode())) == 1
    assert (b"x-request-id", b"inner") not in headers
    assert (b"content-type", b"text/plain") in headers


def test_correlation_binds_websockets_and_ignores_lifespan() -> None:
    seen: list[tuple[str, str | None]] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append((scope["type"], current_request_id()))

    app = RequestCorrelationMiddleware(inner)
    socket = {
        **http_scope(headers=((REQUEST_ID_HEADER, "socket-1"),)),
        "type": "websocket",
    }

    call(app, socket)
    call(app, {"type": "lifespan"})

    assert seen == [("websocket", "socket-1"), ("lifespan", None)]


def access_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == ACCESS_LOGGER_NAME]


def test_access_log_has_one_structured_record_without_request_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=ACCESS_LOGGER_NAME)

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        scope["route"] = Route("/items/{item_id}", endpoint=inner)
        await responding(status=201)(scope, receive, send)

    app = RequestCorrelationMiddleware(AccessLogMiddleware(inner))
    headers = ((REQUEST_ID_HEADER, "access-1"), ("Authorization", f"Bearer {_PRIVATE}"))

    call(app, http_scope(method="POST", headers=headers))

    [record] = access_records(caplog)
    fields = vars(record)
    assert record.levelno == logging.INFO
    assert record.getMessage() == "HTTP request completed"
    assert fields["event"] == "runtime.http_request"
    assert fields["http_method"] == "POST"
    assert fields["http_route"] == "/items/{item_id}"
    assert fields["http_status"] == 201
    assert fields["request_id"] == "access-1"
    assert isinstance(fields["duration_ms"], float)
    assert fields["duration_ms"] >= 0
    assert _PRIVATE not in repr(fields)
    assert "/items/7" not in repr(fields)
    assert "203.0.113.9" not in repr(fields)


def test_access_log_without_route_and_with_unknown_method(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=ACCESS_LOGGER_NAME)

    call(AccessLogMiddleware(responding(status=404)), http_scope(method="BREW"))

    [record] = access_records(caplog)
    assert vars(record)["http_method"] == "_OTHER"
    assert vars(record)["http_route"] is None
    assert vars(record)["http_status"] == 404
    assert vars(record)["request_id"] is None


@pytest.mark.parametrize(
    ("path", "root_path"),
    [("/health/live", ""), ("/health/ready", ""), ("/api/health/live", "/api")],
)
def test_health_requests_are_logged_at_debug(
    caplog: pytest.LogCaptureFixture, path: str, root_path: str
) -> None:
    caplog.set_level(logging.DEBUG, logger=ACCESS_LOGGER_NAME)

    call(AccessLogMiddleware(responding()), http_scope(path=path, root_path=root_path))

    [record] = access_records(caplog)
    assert record.levelno == logging.DEBUG


@pytest.mark.parametrize(
    ("path", "root_path"),
    [("/health", ""), ("/health/live/x", ""), ("/other/health/live", "/api")],
)
def test_other_paths_are_not_health_requests(path: str, root_path: str) -> None:
    assert not is_health_request(http_scope(path=path, root_path=root_path))


def test_access_log_records_failures_before_a_response_as_500(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=ACCESS_LOGGER_NAME)

    async def failing(scope: Scope, receive: Receive, send: Send) -> None:
        raise RuntimeError(_PRIVATE)

    with pytest.raises(RuntimeError):
        call(AccessLogMiddleware(failing), http_scope())

    [record] = access_records(caplog)
    assert vars(record)["http_status"] == 500
    assert record.exc_info is None
    assert _PRIVATE not in record.getMessage()


def test_access_log_keeps_the_sent_status_when_failing_later(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=ACCESS_LOGGER_NAME)

    async def failing(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError(_PRIVATE)

    with pytest.raises(RuntimeError):
        call(AccessLogMiddleware(failing), http_scope())

    [record] = access_records(caplog)
    assert vars(record)["http_status"] == 200


def test_access_log_skips_cancelled_requests_and_other_scopes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=ACCESS_LOGGER_NAME)

    async def cancelled(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            raise asyncio.CancelledError

    app = AccessLogMiddleware(cancelled)
    with pytest.raises(asyncio.CancelledError):
        call(app, http_scope())
    call(app, {**http_scope(), "type": "websocket"})

    assert not access_records(caplog)
