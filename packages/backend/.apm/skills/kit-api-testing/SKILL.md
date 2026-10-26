---
name: kit-api-testing
description: Use when adding black-box API tests with Postman or Newman, Bruno, .http files, Schemathesis, or contracts.
license: MIT
---

# Test an HTTP API from the outside

## Procedure

1. Inventory existing API tests and the published OpenAPI description. Place
   each new check in one layer of the [test strategy](references/guide.md);
   avoid repeating schema assertions by hand.
2. Add property-based contract tests with the
   [Schemathesis template](assets/test_openapi_contract.py.template) against
   an app built with test settings and fake adapters; follow
   [Schemathesis](references/schemathesis.md) for setup, budgets, and triage.
3. Cover the negative matrix in
   [contracts, negative cases, and CI](references/contracts-negative-ci.md):
   authentication, authorization, validation, limits, protocol errors,
   idempotency, CORS, and host checks.
4. For deployed smoke tests, adapt the
   [Postman collection](assets/shop.postman_collection.json.template) and
   [environment](assets/local.postman_environment.json.template), or Bruno
   files, per [collections and files](references/collections.md). Committed
   files hold placeholders only; tokens come from the CI secret store.
5. Keep an [.http file](assets/shop.http.template) for manual exploration and
   bug reports; it is not a CI suite.
6. When independent consumers exist, add consumer-driven contract
   verification to the provider pipeline.
7. Wire CI: in-process and property tests on every pull request, contract
   verification in the provider pipeline, collection smoke tests after
   deployment once readiness passes, larger property budgets on a schedule.
8. Reproduce each failure with a regular regression test before fixing it.

## Acceptance gates

- Every operation in the OpenAPI description is exercised by Schemathesis
  with no server errors, undocumented statuses, or schema violations.
- Each negative case in the matrix has a test that asserts status, problem
  media type, and contract headers.
- Collection and environment files parse, use Collection Format v2.1, and
  contain no hosts beyond local placeholders, tokens, or personal data.
- Generated and smoke requests run only against in-process apps or
  disposable environments.
- Tool versions are pinned in the project's lock files; CI publishes reports.
