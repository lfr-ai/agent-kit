# FastAPI service guide: failure modes, anti-patterns, verification

Reviewed 2026-10-23. Topic detail lives in the sibling references:
[layout](service-layout.md), [lifespan and dependencies](lifespan-and-dependencies.md),
[middleware](middleware.md), [errors](errors-and-responses.md),
[operations](operations.md), and [testing](testing.md).

## Failure modes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Latency spikes for every route under load | Blocking call in `async def` | Make the handler `def`, use an async client, or offload to a thread |
| Routes missing from OpenAPI and returning 404 | Router defined but never included | Include it; run `check_fastapi_wiring.py` |
| Tests pass, production fails at first request | Resource built at import or tests skipped lifespan | Factory plus lifespan; `with TestClient(...)` |
| Browser calls with cookies accepted from any site | CORS credentials with wildcard origin | Explicit origins |
| 500 responses without CORS or request id headers | Expected errors raised as plain exceptions | Raise `ServiceError` subclasses mapped in handlers |
| 400 "error parsing the body" for large uploads | Body limit raised a non-HTTP exception from `receive` | Raise an `HTTPException` subclass |
| Rate limit ineffective with several workers | Per-process in-memory store | Shared store behind `RateLimitStore` ([rate limiting](rate-limiting.md)) |
| All traffic rejected while the limiter store is down | Fail-closed default policy | Choose the failure mode per policy; alert on `failed_*` |
| Every replica restarted during a database outage | Liveness checks dependencies | Move checks to readiness |
| Tokens or personal data in logs | Logging headers, query strings, or bodies | Access log fields only; redact at the boundary |

## Anti-patterns

- `app = FastAPI()` plus module-level clients, pools, or settings.
- `@app.on_event` handlers next to a lifespan (they are ignored).
- Handlers that open sessions, call several repositories, and decide business
  outcomes; move that into a use case.
- `BaseHTTPMiddleware` for request id or context propagation.
- A global `Exception` handler that returns `str(error)` to clients.
- `allow_origins=["*"]` copied from a tutorial into production settings.
- One `schemas.py` imported by every layer; DTOs belong to their router.

## Verification

```text
python check_fastapi_wiring.py src/<package>
python check_response_model_redundancy.py src/<package>   # kit-api-contracts
python check_backend_wiring.py src --package <package>    # kit-python-service
pytest tests/api -q
```

Static checks prove shape, not behavior: keep the HTTP tests from
[testing](testing.md). The wiring checker matches routers by file stem and
name; two modules with the same stem in different packages can mask a missing
inclusion, and dynamically built routers are not seen.

## Primary sources

- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [Starlette documentation](https://starlette.dev/)
- [ASGI specification](https://asgi.readthedocs.io/en/latest/)
- [OWASP API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
