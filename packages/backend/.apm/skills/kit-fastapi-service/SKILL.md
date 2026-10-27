---
name: kit-fastapi-service
description: Use when wiring or reviewing a FastAPI app factory, lifespan, DI, routers, middleware, errors, or health.
license: MIT
---

# Build and wire a production FastAPI service

## Procedure

1. Read the existing entry point, settings, routers, middleware, and tests.
   Place every module in a layer with the
   [service layout](references/service-layout.md); keep business rules in the
   core per `kit-hexagonal-architecture` and `kit-domain-model`.
2. Build the app in one factory ([app.py](assets/app.py.template)) that takes
   validated settings, a container factory, and shared stores as keyword
   arguments. Serve it with `uvicorn --factory` from
   [main.py](assets/main.py.template); nothing runs at import time.
3. Open and close resources in the lifespan, never in `on_event` or at import.
   Expose the typed [container](assets/dependencies.py.template) of
   [application ports](assets/ports.py.template) through
   `Annotated[..., Depends(...)]` aliases per
   [lifespan and dependencies](references/lifespan-and-dependencies.md).
4. Keep handlers thin ([router example](assets/items.py.template)): parse,
   call one port, map the result. Register routers under a versioned prefix;
   follow `kit-api-contracts` for status codes and response models.
5. Choose `async def` only when every call awaits or is non-blocking; use plain
   `def` handlers or dependencies for blocking libraries.
6. Install middleware in the documented order with the
   [middleware module](assets/middleware.py.template) and
   [rate limiter](assets/rate_limit.py.template); see
   [middleware order](references/middleware.md). CORS lists explicit origins.
   Size application rate limits per [rate limiting](references/rate-limiting.md):
   route policies, per-subject limits after authentication, an explicit
   failure mode, and the shared GCRA
   [Redis store](assets/redis_rate_limit.py.template) whenever more than one
   process serves traffic; edge limits stay in `kit-edge-networking` and
   consumer quotas in `kit-api-gateway`.
7. Raise framework-free [service errors](assets/exceptions.py.template) and map
   them once in [errors.py](assets/errors.py.template) through the
   [problem builder](assets/problems.py.template); see
   [errors and responses](references/errors-and-responses.md).
8. Add [health endpoints](assets/health.py.template): liveness without
   dependencies, readiness with bounded probes, per
   [operations](references/operations.md). Configure OpenAPI metadata and
   graceful shutdown there too.
9. Load the [HTTP settings facet](assets/settings.py.template) through the
   project's settings class (`kit-config`); validation rejects wildcard hosts
   and origins.
10. Test through the factory with fake adapters
    ([test template](assets/test_api.py.template),
    [testing guide](references/testing.md)): success, each error mapping,
    limits, headers, readiness failure, and dependency overrides. Run the
    [store contract tests](assets/test_redis_rate_limit.py.template) against
    a real Redis-compatible container.
11. Run [check_fastapi_wiring.py](assets/check_fastapi_wiring.py) on the
    package, then the project gate. Review the
    [failure modes and anti-patterns](references/guide.md).

```text
python check_fastapi_wiring.py src/shop
python check_fastapi_wiring.py src/shop --rule blocking-call --exclude scripts
python check_fastapi_wiring.py --self-test
```

The checker prints `path:line: [rule] message` and exits 0 clean, 1 with
findings, 2 on usage or input errors. It parses source only; it does not
prove runtime wiring.

## Acceptance gates

- One factory builds the app; tests and production call it with different
  container factories. No module-level app, client, or pool is created at import.
- Every router is included under a versioned prefix or a deliberate
  unversioned path (health), and the checker reports no findings.
- Every error response is `application/problem+json`, including validation,
  unknown routes, limits, and unexpected errors; 5xx bodies are generic.
- Middleware order matches the reference; CORS never combines credentials
  with a wildcard; body size and rate limits have tests.
- Rate limiting uses a shared store when more than one process serves
  traffic, keys by verified subject or proxy-resolved address, sets the
  failure mode deliberately, returns 429 with `Retry-After`, and emits a
  metric per policy and outcome without caller identifiers.
- Liveness has no dependency calls; readiness returns 503 within the probe
  deadline when a dependency fails.
- Logs carry the request identifier and never headers, query strings, bodies,
  or tokens.
