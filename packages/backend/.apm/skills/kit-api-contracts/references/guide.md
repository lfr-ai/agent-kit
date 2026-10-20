# API contract guide

## Purpose

Support deliberate API changes: make compatibility decisions explicit, provide
verification steps, and prepare recovery paths before shipping breaking
behavior. Topic detail lives in the sibling references.

## Acceptance gates

- Generate the description from its owner and compare it with the released
  contract; retain the snapshot and diff according to the repository's workflow.
- Backward-compatibility analysis is recorded per
  [compatibility rules](compatibility-rules.md) and consumer compatibility
  tests pass.
- New required fields are avoided, or shipped behind a new version with a
  migration path.
- A consumer notification and deprecation window are documented for breaking
  changes ([versioning and deprecation](versioning-deprecation.md)).

## Failure modes and risk

- Removed or renamed paths and operations that clients still call.
- New required fields that cause failures in older clients.
- Removed enum values or changed meanings that affect real consumers.
- Changed units, field types, or pagination semantics that corrupt downstream
  processing ([pagination](pagination.md)).
- Error format changes that break client error handling
  ([problem details](problem-details.md)).
- Retries that duplicate side effects ([idempotency](idempotency.md)).

## Verification prerequisites

- Obtain a representative set of consumer requests or contract tests.
- Export the current published OpenAPI or JSON Schema snapshot.
- Use the consumer's declared schema validator and diff tool, or the bundled
  [compare_openapi.py](../assets/compare_openapi.py) for JSON descriptions.
  Resolve supported references under the approved network policy. Path-level
  parameters, schemas, required fields, security requirements, and response
  content matter as much as removed paths, methods, or status codes.
- Run provider contract tests per
  [OpenAPI contract testing](openapi-contract-testing.md).

## Negative cases to exercise

- Missing required field and extra unknown field in a strict request schema.
- Invalid enum value and out-of-range numeric values.
- Authentication and authorization failures and rate limiting responses.
- Unknown resource, version conflict, and reused idempotency key.

## Recovery and mitigation

- Follow the published API versioning policy. Keep a compatibility adapter only
  for actual old consumers, with tests and a removal condition.
- Use an existing rollout mechanism only when the change needs it.
- Roll back the deployment if client outages start and publish a review with a
  resolved timeline.

## Scope and limits

This guide covers schema and contract change management. It does not guarantee
runtime stability or client-side behavior, and it does not replace load or
integration testing in production-like environments.

Use the [contract evidence record](../assets/contract-review.md.template).

## Sources

- [OpenAPI Specification 3.1.1](https://spec.openapis.org/oas/v3.1.1.html)
- [Semantic Versioning 2.0.0](https://semver.org/)
- [Google Cloud API design guide](https://cloud.google.com/apis/design)
