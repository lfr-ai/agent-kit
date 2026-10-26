# Lifespan, dependency injection, and sync versus async

Reviewed 2026-10-23 against the FastAPI and Starlette documentation.

## Lifespan

- Pass `lifespan=` to `FastAPI(...)`. Code before `yield` runs once before the
  first request; code after `yield` runs at shutdown, after the server stops
  accepting connections and in-flight requests finish or time out.
- Yield a mapping (lifespan state) such as `{"container": container}`; Starlette
  copies it into each `request.state`. This avoids module globals and
  `app.state` mutation from tests.
- Open resources with `async with` inside the lifespan so a failed startup
  closes what already opened. Startup failure stops the process; prefer that
  over serving requests that cannot work.
- `@app.on_event("startup")` and `("shutdown")` are deprecated and ignored when
  a lifespan is set. The checker reports them.
- Lifespan runs once per worker process. Use a shared store for state that must
  be consistent across workers (rate limits, caches, locks).

## Dependency injection

| Need | Use |
| --- | --- |
| Process-wide service or adapter | Field on the frozen `Container`, exposed by a dependency function |
| Per-request value (principal, tenant, transaction) | Dependency function, optionally with `yield` for cleanup |
| Configuration in a handler | Inject the specific setting through the container, never `Settings()` in a handler |
| Test replacement | `app.dependency_overrides[original] = replacement` |

- Declare aliases once: `CatalogDep = Annotated[ItemCatalog, Depends(get_catalog)]`.
  `Annotated` avoids `= Depends()` defaults, which linters flag and which hide
  the real parameter type.
- Depend on ports (`Protocol`), not adapters. The handler signature then
  documents exactly which collaborators it uses.
- FastAPI caches a dependency once per request by default; set
  `use_cache=False` only when each use must re-run.
- Since FastAPI 0.118.0 the exit code of a dependency with `yield` runs after
  the response is sent (`Depends(scope="request")`, the default); declare
  `scope="function"` to release a resource as soon as the handler returns.
  Exceptions raised after `yield` cannot change the response.
- Do not build a service locator (`container.get("name")`). Typed fields keep
  wiring errors visible to the type checker.

## Sync versus async

| Code in the handler or dependency | Declare |
| --- | --- |
| Only `await`-ed async I/O or pure computation under a millisecond | `async def` |
| A blocking library (sync DB driver, `requests`, file I/O, JWKS fetch) | `def`; FastAPI runs it in a worker thread |
| CPU-heavy work | A process pool or task queue, not the request path |
| Mixed | `async def` plus `anyio.to_thread.run_sync` around the blocking call |

A blocking call inside `async def` stalls every request on that worker. The
worker thread pool is bounded (40 threads by default in AnyIO), so a large
number of slow sync handlers also queues requests; size it deliberately.

## Graceful shutdown

1. The orchestrator marks the instance unready or removes it from the load
   balancer; a short pre-stop delay lets that propagate.
2. The server receives `SIGTERM`, stops accepting connections, and waits for
   in-flight requests up to its graceful timeout
   (`--timeout-graceful-shutdown` for Uvicorn).
3. Lifespan shutdown closes pools and clients in reverse order.

Keep the orchestrator's termination grace period longer than the pre-stop
delay plus the server timeout plus the lifespan shutdown time.

## Primary sources

- [FastAPI: Lifespan events](https://fastapi.tiangolo.com/advanced/events/)
- [FastAPI: Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [FastAPI: Dependencies with yield](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/)
- [FastAPI: Advanced dependencies, yield and scope](https://fastapi.tiangolo.com/advanced/advanced-dependencies/)
- [FastAPI: Concurrency and async / await](https://fastapi.tiangolo.com/async/)
- [Starlette: Lifespan](https://starlette.dev/lifespan/)
- [AnyIO: Working with threads](https://anyio.readthedocs.io/en/stable/threads.html)
- [Uvicorn: Settings](https://uvicorn.dev/settings/)
