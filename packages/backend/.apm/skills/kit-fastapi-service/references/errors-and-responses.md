# Errors, response models, and status codes

Reviewed 2026-10-23. The problem details envelope, problem type catalog, and
compatibility rules belong to the `kit-api-contracts` skill; this reference
covers how a FastAPI service produces them.

## Exception hierarchy

| Layer | Raises | Example |
| --- | --- | --- |
| Core and application | `ServiceError` subclasses with caller-safe messages | `NotFoundError("item 'x' does not exist")` |
| Adapters | Port exceptions, translated from driver errors | `DependencyUnavailableError` from a pool timeout |
| Presentation | Nothing new; handlers map classes to problem types | `errors.py` |

[exceptions.py.template](../assets/exceptions.py.template) holds the
framework-free base; [errors.py.template](../assets/errors.py.template) maps
each class with a `ProblemSpec` table and walks the class hierarchy, so a new
subclass inherits its parent's status until it gets its own entry.

## Mapping table

| Error class | Status | Problem slug |
| --- | --- | --- |
| `NotFoundError` | 404 | `not-found` |
| `ConflictError` | 409 | `conflict` |
| `RuleViolationError` | 422 | `rule-violation` |
| `PermissionDeniedError` | 403 | `forbidden` |
| `DependencyUnavailableError` | 503 | `unavailable` |
| `RequestValidationError` | 422 | `validation`, with `errors[].pointer` |
| Starlette `HTTPException` | its status | `about:blank`, headers preserved |
| Anything else | 500 | `internal`, generic detail |

Keep `HTTPException` headers: `WWW-Authenticate` on 401, `Allow` on 405, and
`Retry-After` on 429 or 503 are part of the contract.

## Handler rules

- Register handlers for `ServiceError`, `RequestValidationError`, Starlette's
  `HTTPException` (FastAPI's subclasses it), and `Exception`.
- The `Exception` handler runs in `ServerErrorMiddleware`, outside every user
  middleware; Starlette re-raises the error afterwards so the server logs the
  traceback. Do not log it again in the handler.
- Never put exception text, SQL, stack traces, file paths, or provider
  responses in `detail`. `ServiceError.message` is the only message that
  reaches clients, so write it for them.
- Validation errors report locations (`/body/lines/0/quantity`), not the
  submitted values, which may be secrets or personal data.

## Response models and status codes

- The return annotation is the response model. Add `response_model=` only to
  filter a different type or to disable it with `None`
  (`check_response_model_redundancy.py` in `kit-api-contracts`).
- Set non-200 success codes on the decorator (`status_code=201`), and document
  error codes in `responses=` so OpenAPI lists them.
- Use `Response` injection to set headers or a dynamic status, as the
  readiness handler does for 503.
- Return `204` with no body for deletes; never return a domain or ORM object.

## Primary sources

- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [RFC 9110: HTTP Semantics, status codes](https://www.rfc-editor.org/rfc/rfc9110.html#name-status-codes)
- [FastAPI: Handling errors](https://fastapi.tiangolo.com/tutorial/handling-errors/)
- [FastAPI: Response model, return type](https://fastapi.tiangolo.com/tutorial/response-model/)
- [Starlette: Exceptions](https://starlette.dev/exceptions/)
