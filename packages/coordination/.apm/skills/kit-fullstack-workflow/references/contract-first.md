# Contract-first design

The contract is the single source of truth that every layer builds against:
an OpenAPI document for HTTP, a schema for events or messages, a typed
interface shared through a published package. Writing it first turns design
disagreements into cheap document edits instead of expensive rework.

## Choose the authoritative source

| Interface | Authoritative source | Consumers derive |
| --- | --- | --- |
| HTTP API | OpenAPI document in the API owner's repository | Server stubs or validation, typed clients, contract tests, docs |
| Events and messages | Schema per message type with a version | Producer serializers, consumer parsers, compatibility checks |
| Shared database | Migrations owned by one service | Read models in other services through a view or API, not shared tables |
| In-process module boundary | Typed interface in the owning package | Implementations and test doubles |

There is exactly one authoritative source per interface. If the backend code
generates the OpenAPI document, the generated document is still reviewed and
committed as the contract, and changes start there conceptually: write or
update the specification change first, then make the code produce it.

## Design checklist for an HTTP resource

- **Naming**: plural nouns for collections (`/orders`), stable identifiers in
  the path (`/orders/{orderId}`), actions as sub-resources only when they are
  not plain state changes (`/orders/{orderId}/cancellation`).
- **Methods and status codes**: `GET` safe, `PUT` and `DELETE` idempotent,
  `POST` for creation (201 with `Location`) or non-idempotent actions, 204 for
  success without body, 404 versus 403 decided deliberately.
- **Representation**: explicit `required` lists; nullable only when absence
  and null mean different things; formats for dates (`date`, `date-time`
  in UTC), money as integer minor units or decimal strings with currency.
- **Collections**: pagination (cursor preferred for changing data), maximum
  page size, stable sort order, filter parameter names.
- **Errors**: one problem-details shape for every error, with a stable `type`
  identifier per error kind and field-level details for validation failures.
- **Concurrency**: `ETag` and `If-Match` for updates where lost updates
  matter; `409` or `412` documented.
- **Idempotency**: an idempotency key header for retried `POST` requests that
  create resources or move money.
- **Authorization**: required scopes or roles per operation in the security
  requirements; which fields are visible to which roles.
- **Limits**: request size, rate limits and timeouts the client must handle.
- **Examples**: realistic, neutral examples for each operation; never real
  personal data or secrets.

## Additive versus breaking

| Change | Classification |
| --- | --- |
| New optional request field, new response field, new operation, new enum value in a response the client ignores | Additive, if clients tolerate unknown fields |
| New required request field, removed or renamed field, changed type or format, narrowed enum, changed status code or error type, new required header | Breaking |
| New enum value that clients switch on exhaustively | Breaking in practice; treat as breaking |
| Tightened validation (shorter max length) | Breaking for existing data and clients |

Additive changes still need the frontend to tolerate unknown fields. Breaking
changes need either a new version (path, media type or header, following the
project's convention) or the expand-migrate-contract sequence in
[sequencing](sequencing.md).

## Contract tests

- **Provider side**: validate real responses from the backend against the
  specification in the backend's test suite, including error responses.
- **Consumer side**: the frontend's tests use fixtures validated against the
  same specification, so a fixture cannot describe a shape the server will
  never send.
- **Drift check in CI**: regenerate clients and fail the build if the result
  differs from what is committed, or if the server's generated document
  differs from the reviewed one.

## Review the contract

Reviewers: API owner, at least one consumer owner, and security for new
authorization rules. Record the outcome in the
[contract change record](../assets/contract-change.md.template). Start new
resources from the [OpenAPI template](../assets/openapi.yaml.template).

## Sources

- [OpenAPI Specification 3.1](https://spec.openapis.org/oas/v3.1.0)
- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 3339: Date and Time on the Internet](https://www.rfc-editor.org/rfc/rfc3339)
- [JSON Schema](https://json-schema.org/specification)
