# OpenAPI 3.1 contracts and contract testing

The OpenAPI description is the published contract. Treat it as a build
artifact that is generated (or hand-maintained), validated, diffed against the
released version, and exercised by tests.

## OpenAPI 3.1 essentials

- `openapi: 3.1.x` uses JSON Schema 2020-12 for schemas. Nullable values are
  written `type: [string, "null"]`; the 3.0 `nullable` keyword no longer exists.
- `examples` (array) replaces `example` inside schemas; media-type `example` and
  `examples` still exist on request and response objects.
- `jsonSchemaDialect` sets the default dialect; `$schema` may appear in a schema.
- `webhooks` describe callbacks the API sends without a preceding request.
- `components.pathItems` allows reusable path items.
- Reuse with `$ref` to `#/components/...`; keep every error response pointing
  at one shared `Problem` schema.

Start from [openapi.yml.template](../assets/openapi.yml.template).

## Authoring rules

- Every operation has a unique `operationId`, a summary, tags, and explicit
  responses for success and each documented error status.
- Every request body and response has a schema; avoid free-form `object`.
- Mark required properties explicitly and set `additionalProperties: false` on
  request schemas when unknown fields must be rejected. Leave response schemas
  open so adding fields stays compatible for tolerant clients.
- Document headers (`Idempotency-Key`, `ETag`, `Deprecation`, `Sunset`,
  `Retry-After`) on the operations that use them.
- Describe security schemes and apply them globally or per operation.

## Generated contracts (FastAPI)

FastAPI derives the description from route signatures and response models.
Export it in CI (`app.openapi()` serialized to JSON) and commit the released
snapshot. Do not declare the same model twice: when the return annotation
already is the response model, `response_model=` duplicates it.
[check_response_model_redundancy.py](../assets/check_response_model_redundancy.py)
flags such decorators. Use `response_model` only when the returned object
differs from the documented model (filtering an internal object), or set
`response_model=None` to disable generation deliberately.

## Contract test layers

1. **Static validation**: validate the description against the OpenAPI 3.1
   schema with the project's validator.
2. **Compatibility diff**: compare the candidate with the released snapshot.
   [compare_openapi.py](../assets/compare_openapi.py) reports common breaking
   changes in JSON descriptions with only the standard library; use a dedicated
   diff tool when the project has one.
3. **Provider tests**: call the application in-process and assert status codes,
   media types, headers, and that bodies validate against the documented
   schema. See [test_router_contract.py.template](../assets/test_router_contract.py.template).
4. **Consumer tests**: consumers record the requests and fields they rely on;
   the provider runs them in CI before release.
5. **Property-based fuzzing** (optional): generate requests from the schema to
   find server errors and schema violations.

## Release gate

- The candidate description validates.
- The compatibility diff shows no unapproved breaking change.
- Provider contract tests pass for every documented status.
- Changelog and migration notes cover every intentional change.

## Sources

- [OpenAPI Specification 3.1.1](https://spec.openapis.org/oas/v3.1.1.html)
- [OpenAPI: Migrating from 3.0 to 3.1](https://learn.openapis.org/upgrading/v3.0-to-v3.1.html)
- [JSON Schema 2020-12](https://json-schema.org/draft/2020-12)
- [FastAPI: Response model](https://fastapi.tiangolo.com/tutorial/response-model/)
- [FastAPI: Extending OpenAPI](https://fastapi.tiangolo.com/how-to/extending-openapi/)
- [FastAPI: Testing](https://fastapi.tiangolo.com/tutorial/testing/)
