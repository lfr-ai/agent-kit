---
description: Apply to OpenAPI, AsyncAPI, and GraphQL contract files.
applyTo: "**/openapi*.json,**/openapi*.yaml,**/openapi*.yml,**/asyncapi*.json,**/asyncapi*.yaml,**/asyncapi*.yml,**/redocly.yaml,**/*.graphql,**/*.gql"
---

- Treat the contract file as the public interface: change it deliberately, review it like code, and keep it in sync with the implementation by generation or contract tests.
- Declare the specification version explicitly (for example OpenAPI 3.1 or AsyncAPI 3.0) and use only constructs that version defines.
- Give every operation a unique, stable `operationId`, a summary, tags, and documented success and error responses.
- Define reusable schemas, parameters, and responses under `components` and reference them with `$ref` instead of duplicating shapes.
- Use one error schema across operations (such as RFC 9457 problem details) with stable machine-readable codes.
- Mark required fields, formats, enums, bounds, and nullability explicitly; reject unknown fields only where the contract says so.
- Document authentication with security schemes, never with example tokens or real host names.
- Keep examples synthetic and valid against their schemas.
- Additions are compatible; removing or renaming fields, tightening validation, or changing types or status codes is breaking and needs a new version or a deprecation period.
- In GraphQL, deprecate fields with `@deprecated(reason: ...)` before removal and prefer nullable additions.
- Lint contracts with the project's configured linter and diff against the last released contract before merging.
- Use the `kit-api-contracts` skill for contract design and compatibility review.
