# Consumer contracts, negative cases, and CI wiring

Reviewed 2026-10-23.

## Consumer-driven contracts

- A consumer records the requests it sends and the response fields it reads;
  the provider replays those interactions in its own pipeline. Breaking a
  field nobody reads passes; breaking one a consumer reads fails before
  release.
- Use Pact (or the project's established tool) when independent teams own
  consumers and release separately. With one team and one client, schema
  compatibility checks from `kit-api-contracts` plus provider tests are
  usually enough.
- Provider states ("item sku-1 exists") are set up through test-only hooks
  on a test build, never through production endpoints.
- Publish verification results so a consumer can check "can I deploy"
  before releasing.

## Negative cases every API suite needs

| Area | Case | Expected |
| --- | --- | --- |
| Authentication | No token, malformed token, expired token, wrong audience | 401 with `WWW-Authenticate` |
| Authorization | Valid token without permission; another tenant's object | 403, or 404 when existence is secret |
| Validation | Missing required field, wrong type, unknown field, out-of-range number, oversized string | 422 problem with pointers |
| Limits | Body over the limit; requests over the rate limit | 413; 429 with `Retry-After` |
| Protocol | Unknown route, wrong method, unsupported media type, missing `Accept` match | 404, 405 with `Allow`, 415, 406 |
| Idempotency | Same key replayed; same key with a different body | Same result; 409 or 422 |
| Headers | Disallowed CORS origin, untrusted `Host` | No CORS headers; 400 |

Every negative response uses the problem details format and leaks no stack
trace, SQL, or token.

## CI wiring

1. Pull request: unit tests, in-process HTTP tests, Schemathesis with a small
   example budget, OpenAPI diff against the released description.
2. Provider pipeline: verify consumer contracts against the build.
3. After deployment to a test environment: wait for readiness, then run the
   collection smoke tests (Newman or Bruno) with secrets from the CI store and
   JUnit reports as artifacts.
4. Scheduled: Schemathesis with a larger budget and stateful tests against a
   disposable environment.

Fail the pipeline on any failed assertion; do not mark API tests as allowed
to fail. Keep tool versions pinned in the project's lock files.

## Primary sources

- [Pact: How Pact works](https://docs.pact.io/getting_started/how_pact_works)
- [Pact: Provider states](https://docs.pact.io/getting_started/provider_states)
- [Martin Fowler: Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html)
- [OWASP Web Security Testing Guide](https://owasp.org/www-project-web-security-testing-guide/)
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
