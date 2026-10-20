---
name: kit-api-contracts
description: Use when designing or changing HTTP API inputs, outputs, status codes, or compatibility behavior.
license: MIT
---

# Change an API contract deliberately

## Procedure

1. Locate the route, schemas, clients, published API description, and
   versioning policy. Record the current wire shape, status codes, headers, and
   error format before editing.
2. Design resources, methods, and status codes per
   [REST resource design](references/rest-resource-design.md).
3. Validate untrusted input at transport entry; do not pass framework request
   objects inward. Define missing, null, malformed, and out-of-range behavior
   separately.
4. Return only intended fields through explicit response models; never expose
   internal models, credentials, or personal data. Let the return annotation be
   the response model and do not repeat it in `response_model=`.
5. Emit every error as [problem details](references/problem-details.md)
   (`application/problem+json`), mapping domain failures to stable problem
   types without stack traces or provider details.
6. Paginate growing collections with opaque cursors per
   [pagination](references/pagination.md).
7. Make retries safe: use idempotent methods or an `Idempotency-Key` per
   [idempotency](references/idempotency.md); document non-idempotent effects.
8. Update the OpenAPI 3.1 description ([template](assets/openapi.yml.template))
   and validate it per
   [OpenAPI contract testing](references/openapi-contract-testing.md).
9. Classify every difference from the released description with
   [compatibility rules](references/compatibility-rules.md), using
   [compare_openapi.py](assets/compare_openapi.py) or the project's diff tool,
   and record decisions in the [contract review](assets/contract-review.md.template).
10. For unavoidable breaking changes, version and deprecate per
    [versioning and deprecation](references/versioning-deprecation.md)
    (`Deprecation`, `Sunset`, and `Link` headers, published timeline).
11. Test successful serialization and representative invalid, unauthorized,
    not-found, conflict, and idempotent-retry cases
    ([contract test template](assets/test_router_contract.py.template)).
12. Update examples, changelog, and migration notes when clients must change.

## Acceptance gates

- The published description validates as OpenAPI 3.1 and every operation has an
  `operationId`, documented success and error responses, and schemas.
- The compatibility diff shows no unapproved breaking change; approved ones
  have a version or deprecation plan and named consumers.
- Every 4xx and 5xx response uses the shared problem schema
  ([JSON Schema](assets/problem-details.schema.json.template)).
- Provider contract tests assert status, media type, headers, and schema
  validity for success and each documented error.
- No route passes a `response_model` identical to its return annotation
  ([check_response_model_redundancy.py](assets/check_response_model_redundancy.py)).

## Failure modes

Removed paths or methods, new required fields, removed enum values, changed
units, altered pagination, inconsistent error envelopes, leaked error details,
and non-idempotent retries that duplicate effects.

## Recovery

Follow the published versioning and rollback policy. Keep a compatibility
adapter only while a real old consumer needs it, with a test and a removal date.

## Assets

| Asset | Purpose |
| --- | --- |
| [openapi.yml.template](assets/openapi.yml.template) | OpenAPI 3.1 contract with pagination, idempotency, and problem responses |
| [problem-details.schema.json.template](assets/problem-details.schema.json.template) | RFC 9457 envelope as JSON Schema 2020-12 |
| [router.py.template](assets/router.py.template) | FastAPI router with explicit models and problem handlers |
| [test_router_contract.py.template](assets/test_router_contract.py.template) | Provider contract tests against the published schema |
| [contract-review.md.template](assets/contract-review.md.template) | Compatibility evidence record |
| [compare_openapi.py](assets/compare_openapi.py) | Standard-library breaking-change report for JSON descriptions |
| [check_response_model_redundancy.py](assets/check_response_model_redundancy.py) | Flags `response_model` equal to the return annotation |

```text
python compare_openapi.py released.json candidate.json
python check_response_model_redundancy.py src --require-type
```

Both print one finding per line and exit 1 on findings. A path-only text diff
cannot certify compatibility; neither can these scripts alone.

## References

- [API contract guide](references/guide.md): gates, verification, recovery.
- [REST resource design](references/rest-resource-design.md)
- [Problem details](references/problem-details.md)
- [Pagination](references/pagination.md)
- [Idempotency keys](references/idempotency.md)
- [Versioning and deprecation](references/versioning-deprecation.md)
- [OpenAPI 3.1 contract testing](references/openapi-contract-testing.md)
- [Backwards-compatibility rules](references/compatibility-rules.md)

Do not call an endpoint backward-compatible based only on its internal Python type.
