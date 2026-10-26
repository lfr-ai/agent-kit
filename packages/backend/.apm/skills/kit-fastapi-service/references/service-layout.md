# FastAPI service layout

Reviewed 2026-10-23. Extends the package layout reference of the
`kit-python-service` skill with the HTTP-specific modules; its dependency rule
still applies.

## Default tree

```text
src/shop/
  __init__.py            # public package API only; export nothing from api/
  main.py                # entry point and HTTP composition root (build_app)
  core/
    exceptions.py        # ServiceError hierarchy, no framework imports
    models.py            # domain records and invariants
  application/
    ports.py             # Protocol ports the HTTP layer and services use
    services.py          # use cases
  infrastructure/        # adapters: database, HTTP clients, queues
  api/
    __init__.py          # empty, or re-export create_app for entry points
    app.py               # create_app factory and lifespan
    dependencies.py      # Container and Depends aliases
    settings.py          # HttpSettings facet
    problems.py          # request id context and problem builder
    errors.py            # exception handlers and problem mapping
    middleware.py        # pure ASGI middleware
    rate_limit.py        # rate limiter and store port
    health.py            # liveness and readiness router
    items.py             # one router module per resource, with its DTOs
tests/
  api/test_api.py        # through create_app with fakes
  contract/              # OpenAPI and consumer contracts
```

## Module responsibilities

| Module | Owns | Must not |
| --- | --- | --- |
| `main.py` | choosing adapters, configuring logging once, calling `create_app` | contain routes or business rules |
| `api/app.py` | FastAPI construction, lifespan, middleware order, router registration | read the environment or build adapters |
| `api/dependencies.py` | typed container and dependency functions | construct adapters |
| `api/<resource>.py` | router, request and response models, thin handlers | import infrastructure |
| `api/errors.py` | mapping service errors to problem types | decide business outcomes |
| `core/exceptions.py` | caller-actionable error classes | import FastAPI or HTTP status codes |

Request and response models live next to the router that serves them, not in a
shared `schemas` package every layer imports. Use `kit-pydantic-v2` for model
rules and `kit-api-contracts` for wire compatibility.

## `__init__` exports

Keep `__init__.py` files empty or limited to an explicit `__all__` of the
package's public entry points. Re-exporting routers or adapters from package
roots creates import cycles and hides layer violations from
`check_backend_wiring.py`.

## Composition root versus container

The composition root is a function (`build_app` plus `open_container`); the
container is the immutable record it returns. A third-party DI framework is
optional: FastAPI's `Depends` plus one frozen dataclass covers most services
and stays type-checkable. Wiring and use-case composition follow the
`kit-hexagonal-architecture` skill.

## Primary sources

- [FastAPI: Bigger applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [FastAPI: Settings and environment variables](https://fastapi.tiangolo.com/advanced/settings/)
- [Uvicorn: application factories](https://uvicorn.dev/settings/#application)
