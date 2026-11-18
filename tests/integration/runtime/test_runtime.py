import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import inspect
import logging
from uuid import UUID

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
import pytest
from starlette.exceptions import HTTPException

from platform_kit_runtime import ProbeUnavailableError, RuntimeConfig, create_app

pytestmark = pytest.mark.integration

_PRIVATE = "synthetic-secret-user@example.invalid"


@dataclass(frozen=True, kw_only=True, slots=True)
class FixedProbe:
    ready: bool

    async def check(self) -> bool:
        return self.ready


@dataclass(frozen=True, kw_only=True, slots=True)
class FailingProbe:
    error: Exception

    async def check(self) -> bool:
        raise self.error


def request(*, app: FastAPI, path: str, method: str = "GET") -> Response:
    async def send() -> Response:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://runtime.test",
        ) as client:
            return await client.request(method, path)

    return asyncio.run(send())


def assert_problem(*, response: Response, status: int, code: str) -> None:
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"type", "title", "status", "detail", "code", "instance"}
    assert body["type"] == "about:blank"
    assert body["status"] == status
    assert body["code"] == code
    assert body["title"]
    assert body["detail"]
    assert UUID(body["instance"].removeprefix("urn:uuid:")).version == 4
    assert _PRIVATE not in response.text
    assert "Traceback" not in response.text


def test_liveness_never_calls_probes() -> None:
    app = create_app(
        config=RuntimeConfig(), probes=(FailingProbe(error=AssertionError(_PRIVATE)),)
    )

    response = request(app=app, path="/health/live")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"status": "ok"}


def test_factory_preserves_consumer_lifespan_and_teardown() -> None:
    async def verify() -> None:
        events: list[str] = []

        @asynccontextmanager
        async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
            assert application is app
            events.append("started")
            try:
                yield
            finally:
                events.append("stopped")

        app = create_app(config=RuntimeConfig(), probes=(), lifespan=lifespan)
        assert events == []
        async with app.router.lifespan_context(app):
            assert events == ["started"]
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://runtime.test"
            ) as client:
                assert (await client.get("/health/live")).json() == {"status": "ok"}
                assert (await client.get("/health/ready")).json() == {"status": "ready"}
        assert events == ["started", "stopped"]

    asyncio.run(verify())


def test_factory_preserves_runtime_metadata_and_security_overrides() -> None:
    app = create_app(config=RuntimeConfig(), probes=())

    assert app.title == "Platform Kit Runtime"
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None
    assert app.router.redirect_slashes is False
    assert app.debug is False


def test_explicit_none_lifespan_keeps_default_resource_free_startup() -> None:
    async def verify() -> None:
        app = create_app(config=RuntimeConfig(), probes=(), lifespan=None)
        async with app.router.lifespan_context(app) as state:
            assert state is None
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://runtime.test"
            ) as client:
                assert (await client.get("/health/live")).json() == {"status": "ok"}
                assert (await client.get("/health/ready")).json() == {"status": "ready"}

    asyncio.run(verify())


def test_consumer_startup_failure_is_not_reported_as_a_healthy_app() -> None:
    async def initialize() -> None:
        msg = "synthetic startup failure"
        raise RuntimeError(msg)

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncGenerator[None]:
        await initialize()
        yield

    app = create_app(config=RuntimeConfig(), probes=(), lifespan=lifespan)

    async def verify() -> None:
        with pytest.raises(RuntimeError, match="synthetic startup failure"):
            async with app.router.lifespan_context(app):
                pytest.fail("An unsuccessful lifespan must not serve requests.")

    asyncio.run(verify())


@pytest.mark.parametrize(
    "probes", [(), (FixedProbe(ready=True),), (FixedProbe(ready=True),) * 2]
)
def test_readiness_succeeds_when_all_probes_succeed(
    probes: tuple[FixedProbe, ...],
) -> None:
    app = create_app(config=RuntimeConfig(), probes=probes)

    response = request(app=app, path="/health/ready")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"status": "ready"}


@pytest.mark.parametrize(
    "probe",
    [FixedProbe(ready=False), FailingProbe(error=ProbeUnavailableError(_PRIVATE))],
)
def test_readiness_failure_is_sanitized_and_logged_once(
    probe: FixedProbe | FailingProbe, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(config=RuntimeConfig(), probes=(FixedProbe(ready=True), probe))
    caplog.set_level(logging.WARNING, logger="platform_kit_runtime")

    response = request(app=app, path="/health/ready")

    assert_problem(response=response, status=503, code="not_ready")
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.__dict__["problem_code"] == "not_ready"
    assert record.__dict__["instance"] == response.json()["instance"]
    assert record.__dict__["failure_reason"] == "probe_failed"
    assert record.exc_info is None
    assert _PRIVATE not in repr(record.__dict__)


def test_unexpected_probe_error_is_private_and_logged_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(
        config=RuntimeConfig(), probes=(FailingProbe(error=RuntimeError(_PRIVATE)),)
    )
    caplog.set_level(logging.ERROR, logger="platform_kit_runtime")

    response = request(app=app, path=f"/health/ready?token={_PRIVATE}")

    assert_problem(response=response, status=500, code="internal_error")
    assert response.json()["title"] == "Internal Server Error"
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.__dict__["instance"] == response.json()["instance"]
    assert record.exc_info is None
    assert _PRIVATE not in repr(record.__dict__)


def test_probe_timeout_cancels_pending_work_and_returns_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stopped = asyncio.Event()

    class WaitingProbe:
        async def check(self) -> bool:
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
            return True

    app = create_app(
        config=RuntimeConfig(readiness_timeout_seconds=0.01),
        probes=(WaitingProbe(),),
    )

    response = request(app=app, path="/health/ready")

    assert_problem(response=response, status=503, code="not_ready")
    assert stopped.is_set()
    assert caplog.records[0].__dict__["failure_reason"] == "timeout"


def test_probes_run_concurrently() -> None:
    ready = asyncio.Event()

    class WaitingProbe:
        async def check(self) -> bool:
            await ready.wait()
            return True

    class ReleasingProbe:
        async def check(self) -> bool:
            ready.set()
            return True

    app = create_app(config=RuntimeConfig(), probes=(WaitingProbe(), ReleasingProbe()))

    response = request(app=app, path="/health/ready")

    assert response.status_code == 200


@pytest.mark.parametrize("value", [None, 0, 1, "ready"])
def test_probe_results_are_not_coerced_to_success(value: bool) -> None:
    app = create_app(config=RuntimeConfig(), probes=(FixedProbe(ready=value),))

    response = request(app=app, path="/health/ready")

    assert_problem(response=response, status=500, code="internal_error")


@pytest.mark.parametrize(
    "path", ["/unknown", "/docs", "/redoc", "/openapi.json", "/health/live/"]
)
def test_unknown_routes_are_sanitized_problems(path: str) -> None:
    app = create_app(config=RuntimeConfig(), probes=())

    response = request(app=app, path=f"{path}?token={_PRIVATE}")

    assert_problem(response=response, status=404, code="not_found")


def test_method_not_allowed_preserves_safe_allow_header() -> None:
    app = create_app(config=RuntimeConfig(), probes=())

    response = request(app=app, path="/health/live", method="POST")

    assert_problem(response=response, status=405, code="method_not_allowed")
    assert response.headers["allow"] == "GET"


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503, 599, 200])
def test_http_exception_details_and_headers_are_not_exposed(status: int) -> None:
    app = create_app(config=RuntimeConfig(), probes=())

    @app.get("/synthetic")
    async def synthetic() -> None:
        raise HTTPException(
            status_code=status, detail=_PRIVATE, headers={"X-Secret": _PRIVATE}
        )

    response = request(app=app, path="/synthetic")

    expected_status = status if status in {400, 403, 429, 500, 503} else 500
    assert_problem(response=response, status=expected_status, code="http_error")
    assert "x-secret" not in response.headers


def test_request_validation_does_not_expose_input_or_locations(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(config=RuntimeConfig(), probes=())

    @app.get("/synthetic")
    async def synthetic(*, count: int) -> int:
        return count

    response = request(app=app, path=f"/synthetic?count={_PRIVATE}")

    assert_problem(response=response, status=422, code="invalid_request")
    assert _PRIVATE not in repr([record.__dict__ for record in caplog.records])


def test_factories_do_not_share_probe_state() -> None:
    healthy = create_app(config=RuntimeConfig(), probes=(FixedProbe(ready=True),))
    unhealthy = create_app(config=RuntimeConfig(), probes=(FixedProbe(ready=False),))

    assert request(app=unhealthy, path="/health/ready").status_code == 503
    assert request(app=healthy, path="/health/ready").status_code == 200
    assert request(app=unhealthy, path="/health/live").status_code == 200


def test_factory_requires_explicit_keyword_dependencies() -> None:
    signature = inspect.signature(create_app)

    with pytest.raises(TypeError):
        signature.bind(RuntimeConfig(), ())
    with pytest.raises(TypeError):
        signature.bind(config=RuntimeConfig())


def test_unexpected_error_cancels_and_awaits_sibling_probe() -> None:
    started = asyncio.Event()
    stopped = asyncio.Event()

    class WaitingProbe:
        async def check(self) -> bool:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
            return True

    class CrashingProbe:
        async def check(self) -> bool:
            await started.wait()
            raise RuntimeError(_PRIVATE)

    app = create_app(config=RuntimeConfig(), probes=(WaitingProbe(), CrashingProbe()))

    response = request(app=app, path="/health/ready")

    assert_problem(response=response, status=500, code="internal_error")
    assert stopped.is_set()


def test_request_cancellation_propagates_and_cleans_up(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        started = asyncio.Event()
        stopped = asyncio.Event()

        class WaitingProbe:
            async def check(self) -> bool:
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()
                return True

        app = create_app(config=RuntimeConfig(), probes=(WaitingProbe(),))
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://runtime.test"
        ) as client:
            task = asyncio.create_task(client.get("/health/ready"))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert stopped.is_set()

    asyncio.run(scenario())

    assert not caplog.records


def test_readiness_recovers_without_rebuilding_app() -> None:
    class RecoveringProbe:
        def __init__(self) -> None:
            self.ready = False

        async def check(self) -> bool:
            return self.ready

    probe = RecoveringProbe()
    app = create_app(config=RuntimeConfig(), probes=(probe,))

    unavailable = request(app=app, path="/health/ready")
    probe.ready = True
    recovered = request(app=app, path="/health/ready")

    assert unavailable.status_code == 503
    assert recovered.status_code == 200


@pytest.mark.parametrize("header_name", ["Allow", "allow", "aLlOw"])
@pytest.mark.parametrize(
    "allow",
    ["GET", "GET, POST", "", "get", _PRIVATE, f"GET\r\nX-Secret: {_PRIVATE}", "\nGET"],
)
def test_only_valid_method_names_survive_allow_header(
    header_name: str, allow: str
) -> None:
    app = create_app(config=RuntimeConfig(), probes=())

    @app.get("/synthetic")
    async def synthetic() -> None:
        raise HTTPException(
            status_code=405, headers={header_name: allow, "X-Secret": _PRIVATE}
        )

    response = request(app=app, path="/synthetic")

    assert_problem(response=response, status=405, code="method_not_allowed")
    assert "x-secret" not in response.headers
    if allow in {"GET", "GET, POST"}:
        assert response.headers["allow"] == allow
    else:
        assert "allow" not in response.headers


@pytest.mark.parametrize(
    "header_name", ["WWW-Authenticate", "www-authenticate", "WwW-AuThEnTiCaTe"]
)
@pytest.mark.parametrize(
    ("challenge", "expected"),
    [
        ("Basic", 'Basic realm="runtime"'),
        ("bAsIc", 'Basic realm="runtime"'),
        ('Basic realm="service"', 'Basic realm="runtime"'),
        ('Basic realm="service", charset="UTF-8"', 'Basic realm="runtime"'),
        (f'Basic realm="{_PRIVATE}"', 'Basic realm="runtime"'),
        (r'Basic realm="escaped \"quote\""', 'Basic realm="runtime"'),
        ("Bearer", "Bearer"),
        ('Bearer realm="service"', "Bearer"),
        ('Bearer realm="service", scope="read write", error="invalid_token"', "Bearer"),
        (f'Bearer error="invalid_token", error_description="{_PRIVATE}"', "Bearer"),
    ],
)
def test_unauthorized_uses_protocol_valid_private_challenge_replacement(
    header_name: str,
    challenge: str,
    expected: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(config=RuntimeConfig(), probes=())

    @app.get("/synthetic")
    async def synthetic() -> None:
        raise HTTPException(
            status_code=401,
            detail=_PRIVATE,
            headers={header_name: challenge, "X-Secret": _PRIVATE},
        )

    response = request(app=app, path="/synthetic")

    assert_problem(response=response, status=401, code="http_error")
    assert response.headers["www-authenticate"] == expected
    assert "x-secret" not in response.headers
    assert _PRIVATE not in repr(dict(response.headers))
    assert len(caplog.records) == 1
    assert _PRIVATE not in repr(caplog.records[0].__dict__)


@pytest.mark.parametrize(
    "challenge",
    [
        "",
        _PRIVATE,
        "Digest",
        "Basic\r\n",
        "\x00Bearer",
        "Bearer secret-token",
        "Basic realm=",
        'Basic realm="unterminated',
        'Basic realm="service",',
        'Basic realm="service", Bearer',
        "Basic realm=service realm=other",
    ],
)
def test_invalid_challenge_becomes_private_server_error(
    challenge: str, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(config=RuntimeConfig(), probes=())

    @app.get("/synthetic")
    async def synthetic() -> None:
        raise HTTPException(
            status_code=401,
            detail=_PRIVATE,
            headers={"www-authenticate": challenge, "X-Secret": _PRIVATE},
        )

    response = request(app=app, path="/synthetic")

    assert_problem(response=response, status=500, code="http_error")
    assert "www-authenticate" not in response.headers
    assert "x-secret" not in response.headers
    assert len(caplog.records) == 1
    assert _PRIVATE not in repr(caplog.records[0].__dict__)


@pytest.mark.parametrize("headers", [None, {}, {"X-Secret": _PRIVATE}])
def test_missing_challenge_never_returns_unauthorized(
    headers: dict[str, str] | None,
) -> None:
    app = create_app(config=RuntimeConfig(), probes=())

    @app.get("/synthetic")
    async def synthetic() -> None:
        raise HTTPException(status_code=401, detail=_PRIVATE, headers=headers)

    response = request(app=app, path="/synthetic")

    assert_problem(response=response, status=500, code="http_error")
    assert "www-authenticate" not in response.headers


@pytest.mark.parametrize(
    ("status", "headers", "header_name", "code"),
    [
        (405, {"Allow": "GET", "allow": _PRIVATE}, "allow", "method_not_allowed"),
        (
            401,
            {"WWW-Authenticate": "Basic", "www-authenticate": _PRIVATE},
            "www-authenticate",
            "http_error",
        ),
    ],
)
def test_ambiguous_case_variant_headers_are_not_forwarded(
    status: int, headers: dict[str, str], header_name: str, code: str
) -> None:
    app = create_app(config=RuntimeConfig(), probes=())

    @app.get("/synthetic")
    async def synthetic() -> None:
        raise HTTPException(status_code=status, detail=_PRIVATE, headers=headers)

    response = request(app=app, path="/synthetic")

    assert_problem(
        response=response, status=500 if status == 401 else status, code=code
    )
    assert header_name not in response.headers
