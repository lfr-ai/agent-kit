# REST resource design

Design resources around nouns that clients understand, use HTTP methods with
their defined semantics, and keep representations stable.

## Resources and URLs

- Collections are plural nouns: `/orders`, `/orders/{order_id}/lines`.
- Identifiers in paths are opaque strings; clients must not parse them.
- Nest at most one level (`/orders/{id}/lines`); link to other resources by
  identifier or URL instead of deeper nesting.
- Use lowercase, hyphen-separated path segments and `snake_case` or `camelCase`
  JSON fields consistently across the whole API.
- Actions that do not map to CRUD become sub-resources or state changes:
  `POST /orders/{id}/confirmation` or `PATCH /orders/{id}` with
  `{"status": "confirmed"}`, not `POST /confirmOrder`.

## Methods

| Method | Semantics | Safe | Idempotent | Typical success |
| --- | --- | --- | --- | --- |
| GET | Retrieve a representation | yes | yes | 200 |
| HEAD | Headers of GET only | yes | yes | 200 |
| POST | Create a subordinate resource or run a processing action | no | no | 201 with `Location`, or 200/202 |
| PUT | Replace the target resource entirely | no | yes | 200 or 204; 201 if created |
| PATCH | Partial update (JSON Merge Patch or JSON Patch) | no | no by definition | 200 or 204 |
| DELETE | Remove the target resource | no | yes | 204 |

Make POST safe to retry with an [idempotency key](idempotency.md).

## Status codes

| Code | Use for |
| --- | --- |
| 200 | Success with a body |
| 201 | Created; include `Location` and usually the representation |
| 202 | Accepted for asynchronous processing; return a status resource URL |
| 204 | Success without a body |
| 400 | Malformed syntax or a request that cannot be parsed |
| 401 | Missing or invalid authentication |
| 403 | Authenticated but not allowed |
| 404 | Resource does not exist (or must not be disclosed) |
| 409 | Conflict with current state (duplicate, version conflict) |
| 412 | `If-Match` precondition failed |
| 415 | Unsupported request media type |
| 422 | Well-formed but semantically invalid content |
| 429 | Rate limited; include `Retry-After` |
| 500 | Unexpected server failure; no internal details |
| 503 | Temporarily unavailable; include `Retry-After` when known |

Every 4xx and 5xx response uses the [problem details](problem-details.md)
format.

## Representations

- Return only intended fields; build response models explicitly rather than
  serializing internal or ORM objects.
- Timestamps: RFC 3339 strings with offset (`2026-01-02T10:00:00Z`).
- Money: decimal string plus currency code, or integer minor units; never a
  binary float.
- Enumerations: lowercase string values documented in the schema; clients must
  tolerate unknown values if the set may grow.
- Absent versus null: decide per field and document it; do not use both to mean
  the same thing.

## Concurrency

Return an `ETag` on GET and require `If-Match` on PUT, PATCH, and DELETE for
resources edited concurrently. Respond 412 on mismatch and 428 when a required
precondition header is missing.

## Collections

Paginate every collection that can grow ([pagination](pagination.md)). Support
filtering with explicit query parameters (`?status=open`) and a documented
`sort` parameter with a stable tie-breaker.

## Sources

- [RFC 9110 - HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 5789 - PATCH method](https://www.rfc-editor.org/rfc/rfc5789.html)
- [RFC 7396 - JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396.html)
- [RFC 6585 - Additional HTTP status codes (428, 429)](https://www.rfc-editor.org/rfc/rfc6585.html)
- [RFC 3339 - Date and time on the Internet](https://www.rfc-editor.org/rfc/rfc3339.html)
- [Google Cloud API design guide](https://cloud.google.com/apis/design)
- [Microsoft REST API guidelines](https://github.com/microsoft/api-guidelines/blob/vNext/azure/Guidelines.md)
