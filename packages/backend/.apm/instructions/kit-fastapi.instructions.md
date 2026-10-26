---
description: Apply to FastAPI application, router, and middleware modules.
applyTo: "**/api/**/*.py,**/main.py,**/middleware/**/*.py"
---

- Build the app in one factory that takes settings and collaborators as arguments; create no app, client, pool, or settings object at import time.
- Open and close resources in the lifespan; do not use `@app.on_event`.
- Inject collaborators with `Annotated[Port, Depends(provider)]` aliases; handlers never construct adapters or read the environment.
- Never call blocking I/O (`time.sleep`, `requests`, sync DB drivers, sync HTTP clients) inside `async def`; use `def` or an async client instead.
- Include every router under a versioned prefix, except deliberate unversioned paths such as health probes.
- Raise framework-free service errors and map them to `application/problem+json` in registered exception handlers; never return exception text to clients.
- Write middleware as pure ASGI classes and keep the documented order; CORS lists explicit origins and never combines credentials with `*`.
- Never log headers, query strings, bodies, or tokens; log the request id.
- Use the `kit-fastapi-service` skill for wiring, middleware, health, and test procedures.
