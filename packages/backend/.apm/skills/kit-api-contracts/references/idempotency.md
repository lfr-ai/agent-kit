# Idempotency keys

Networks fail after the server has acted but before the client sees the
response. Clients then retry. GET, PUT, and DELETE are idempotent by HTTP
semantics; POST and PATCH are not. An idempotency key makes a non-idempotent
request safe to retry.

## Protocol

1. The client generates a unique key per logical operation (a UUID v4 is
   typical) and sends it in the `Idempotency-Key` request header. The IETF
   HTTP API working group draft defines the value as a Structured Field string, for example
   `Idempotency-Key: "8e03978e-40d5-43e8-bc93-6894a57f9324"`.
2. The server stores the key with a fingerprint of the request (method, path,
   caller identity, and a hash of the body) and the eventual response.
3. On a retry with the same key and the same fingerprint, the server returns the
   stored response without acting again.
4. Error handling, as described by the draft:
   - Key required but missing: 400 with problem details.
   - Same key reused with a different request payload: 422.
   - Same key while the first request is still being processed: 409.
5. Keys expire after a documented retention window (for example 24 hours).

## Server implementation notes

- Scope keys per authenticated caller so one client cannot replay another's key.
- Insert the key record and perform the operation in the same transaction, or
  use an insert-if-absent lock row to serialize concurrent duplicates.
- Store only what is needed to replay the response; do not keep secrets from the
  request body.
- Replay the original status code and body, including errors that were the
  result of business validation. Do not cache 5xx responses caused by transient
  failures, so the client can retry them.
- Document which endpoints accept or require the header in the OpenAPI
  description.

## Alternatives

- Natural idempotency: `PUT /orders/{client_generated_id}` creates or replaces,
  so retries are safe without a header.
- Conditional requests: `If-Match` with an `ETag` protects updates from lost
  writes but does not de-duplicate creates.

## Tests

- Two identical POSTs with the same key create one resource and return equal
  responses.
- Same key with a different body returns 422.
- Concurrent requests with the same key produce one effect and one 409 or a
  replayed response.
- Expired keys are treated as new.

## Sources

- [IETF draft: The Idempotency-Key HTTP Header Field](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/)
- [RFC 9110 section 9.2.2 - Idempotent methods](https://www.rfc-editor.org/rfc/rfc9110.html#name-idempotent-methods)
- [RFC 8941 - Structured Field Values for HTTP](https://www.rfc-editor.org/rfc/rfc8941.html)
