# Health, OpenAPI metadata, and running the service

Reviewed 2026-10-23.

## Liveness versus readiness

| Probe | Question | Checks | Failure action |
| --- | --- | --- | --- |
| Liveness `/health/live` | Is the process able to answer? | None beyond the event loop | Restart the container |
| Readiness `/health/ready` | Should this instance receive traffic now? | Bounded probes of required dependencies | Remove from rotation, keep running |
| Startup (optional) | Has initialization finished? | Same as readiness, longer budget | Delay other probes |

- A liveness probe that calls the database restarts every replica during a
  database outage and turns a partial failure into a total one.
- Readiness probes run concurrently with a deadline shorter than the
  orchestrator's probe timeout ([health.py.template](../assets/health.py.template)).
  Report only probe names and booleans; keep error details in logs.
- Exempt probes from rate limiting and authentication; keep them out of the
  public OpenAPI description if clients must not depend on them
  (`include_in_schema=False`).
- Return readiness 503 while draining if the orchestrator does not already
  stop routing on `SIGTERM`.

## OpenAPI metadata

- Set `title`, `version`, and a `description`; give every route an
  `operation_id` and `tags`. `kit-api-contracts` owns compatibility review.
- Serve `/openapi.json` where contract tests and gateways need it; disable
  the interactive docs (`docs_url=None`, `redoc_url=None`) in production or
  protect them, and give them their own Content-Security-Policy.
- Document security schemes through the security dependencies (`kit-auth`)
  so the schema lists them.

## Running

- `uvicorn shop.main:build_app --factory` builds the app per worker without
  import-time side effects. Use one process per container and scale with
  replicas, or a process manager with several workers; each worker runs its
  own lifespan.
- Behind a reverse proxy, enable proxy headers only for the proxy's addresses
  (`--forwarded-allow-ips`), or client addresses and schemes can be spoofed.
- Set `--timeout-graceful-shutdown` below the orchestrator's grace period
  (see [lifespan](lifespan-and-dependencies.md#graceful-shutdown)).
- Set `--limit-concurrency` or rely on the proxy to shed load before memory
  runs out.

## Primary sources

- [Kubernetes: Liveness, readiness, and startup probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [FastAPI: Metadata and docs URLs](https://fastapi.tiangolo.com/tutorial/metadata/)
- [FastAPI: Behind a proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/)
- [Uvicorn: Settings](https://uvicorn.dev/settings/)
- [Uvicorn: Deployment](https://uvicorn.dev/deployment/)
