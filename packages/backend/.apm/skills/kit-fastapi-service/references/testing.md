# Testing a FastAPI service

Reviewed 2026-10-23. Test-first workflow and fakes follow the
`kit-test-first` and `kit-hexagonal-architecture` skills; this reference
covers the HTTP boundary.

## Choose the client

| Need | Client | Lifespan |
| --- | --- | --- |
| Synchronous tests, full app with lifespan | `with TestClient(app) as client:` | Runs on enter and exit |
| Async tests, awaiting other coroutines | `httpx.AsyncClient(transport=httpx.ASGITransport(app=app))` | Not run; override dependencies or use a lifespan manager |
| Real server, network stack, proxies | Uvicorn in a fixture plus `httpx` | Real |
| Property-based contract tests | Schemathesis (`kit-api-testing`) | Run by its ASGI loader |

`TestClient` without `with` skips the lifespan, so container-backed
dependencies fail. Mark async tests with `@pytest.mark.anyio` (AnyIO plugin)
or the project's chosen async plugin; do not mix both.

## Build the app the production way

Call `create_app` with test settings and a container factory that yields
fakes ([test_api.py.template](../assets/test_api.py.template)). Avoid patching
module globals; override by injection:

- Container: pass a fake container factory to `create_app`.
- Single dependency: `app.dependency_overrides[get_container] = fake`; clear
  the mapping after the test when the app is shared.
- Settings: build `HttpSettings.model_validate({...})`; never mutate the
  process environment in tests.

## Cases every service needs

- Success shape and status for each route, compared to the response model.
- Each mapped `ServiceError` returns its status, `application/problem+json`,
  `code`, and `instance` with the request id.
- Validation error pointers; unknown route and method problems.
- Body over the limit (declared and streamed) returns 413 before parsing.
- Rate limit: the request after the limit gets 429 with `Retry-After`;
  health probes stay exempt.
- Untrusted `Host` is rejected; CORS preflight succeeds for a listed origin
  and omits CORS headers for others.
- Security headers present; request id echoed or generated.
- Readiness returns 503 when one probe fails or times out; liveness stays 200.
- Logs (via `caplog`) contain the request id and no tokens or bodies.

## Failure modes in tests

- Shared app across tests leaks `dependency_overrides` or rate-limit counters.
- Tests that pass only because `TestClient` skipped the lifespan.
- Async tests that call blocking code and hide event-loop stalls; run the
  wiring checker on tests too when they define async fixtures.

## Primary sources

- [FastAPI: Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [FastAPI: Async tests](https://fastapi.tiangolo.com/advanced/async-tests/)
- [FastAPI: Testing dependencies with overrides](https://fastapi.tiangolo.com/advanced/testing-dependencies/)
- [FastAPI: Testing events, lifespan](https://fastapi.tiangolo.com/advanced/testing-events/)
- [HTTPX: Transports, ASGI](https://www.python-httpx.org/advanced/transports/)
- [AnyIO: Testing with AnyIO](https://anyio.readthedocs.io/en/stable/testing.html)
