# Problem details error envelope (RFC 9457)

Use one error format for every 4xx and 5xx response: the problem details
object defined by RFC 9457, served as `application/problem+json`.

## Members

| Member | Type | Meaning |
| --- | --- | --- |
| `type` | URI reference | Identifies the problem type; dereferenceable documentation is recommended. Defaults to `about:blank`. |
| `title` | string | Short, human-readable summary of the problem type; should not change between occurrences. |
| `status` | integer | HTTP status code, advisory; must match the actual response status. |
| `detail` | string | Explanation specific to this occurrence, aimed at helping the client fix it. |
| `instance` | URI reference | Identifies this specific occurrence (for example a log or trace reference). |

Extension members are allowed. Clients must ignore extensions they do not
understand. Common extensions:

- `errors`: list of field-level problems, each with a JSON pointer and message.
- `code`: a stable, machine-readable error code within the problem type.
- `trace_id`: correlation identifier for support.

## Example

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/validation",
  "title": "Request validation failed",
  "status": 422,
  "detail": "2 fields are invalid.",
  "instance": "urn:trace:4bf92f3577b34da6",
  "errors": [
    {"pointer": "/lines/0/quantity", "message": "must be greater than 0"},
    {"pointer": "/currency", "message": "must be a 3-letter ISO 4217 code"}
  ]
}
```

## Rules

- Define a small catalog of problem types (validation, not-found, conflict,
  rate-limited, unavailable, internal) and document each at its `type` URI.
- Clients branch on `type` (and `code`), never on `title` or `detail` text.
- `detail` never contains stack traces, SQL, vendor messages, secrets, or
  personal data beyond what the caller sent.
- 5xx responses use a generic `detail`; log the real cause once, server side,
  with the `instance` or trace identifier.
- Map domain errors to problem types in the presentation layer only.
- Keep the same envelope for framework-generated errors (validation failures,
  unknown routes, method not allowed) by overriding default handlers.

## Assets

- [problem-details.schema.json.template](../assets/problem-details.schema.json.template):
  JSON Schema 2020-12 for the envelope with the `errors` extension.
- [router.py.template](../assets/router.py.template): exception handlers that
  emit the envelope.
- [openapi.yml.template](../assets/openapi.yml.template): shared `Problem`
  component referenced by every error response.

## Sources

- [RFC 9457 - Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [RFC 6901 - JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901.html)
- [IANA HTTP Problem Types registry](https://www.iana.org/assignments/http-problem-types/http-problem-types.xhtml)
- [JSON Schema 2020-12](https://json-schema.org/draft/2020-12)
