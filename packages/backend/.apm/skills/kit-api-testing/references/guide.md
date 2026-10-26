# API test strategy guide

Reviewed 2026-10-23. Unit and use-case tests follow `kit-test-first`;
in-process HTTP tests follow the testing reference of `kit-fastapi-service`;
OpenAPI compatibility review belongs to `kit-api-contracts`. This skill covers
the tests that exercise the API as a black box.

## Layers

| Layer | Question answered | Tool | Runs |
| --- | --- | --- | --- |
| In-process HTTP tests | Do handlers, middleware, and error mapping behave? | pytest with `TestClient` or `httpx` | Every commit |
| Schema-driven property tests | Does every operation honor its OpenAPI contract for generated inputs? | Schemathesis | Every commit (bounded examples), nightly (more) |
| Consumer-driven contracts | Does the provider still satisfy what each consumer actually uses? | Pact or a recorded-interaction suite | Provider and consumer pipelines |
| Collection smoke tests | Does a deployed environment answer correctly end to end? | Postman with Newman, Bruno CLI, or `.http` files | After each deployment |
| Exploratory requests | What does this endpoint do right now? | `.http` files or Bruno in the editor | Manually |

## Choosing a collection tool

| Need | Choose |
| --- | --- |
| Team already uses Postman workspaces, needs Newman reports in CI | Postman collection v2.1 plus Newman |
| Collections reviewed in pull requests as plain files, no cloud account | Bruno (`.bru` files, `bru run` CLI) |
| A handful of manual requests next to the code | `.http` files |
| Generated coverage of every operation and parameter | Schemathesis, not a hand-written collection |

Keep one source of truth per purpose. A hand-written collection that repeats
every schema assertion drifts; let Schemathesis own schema conformance and
keep collections for flows, smoke checks, and negative cases.

## Failure modes

- Secrets committed in environment files or collection variables.
- Collections that pass against an empty database and prove nothing.
- Property tests that hit shared or production data.
- Negative tests missing, so only the happy path is covered.
- CI that runs smoke tests before the deployment is ready.

## Verification

- JSON templates parse, use the v2.1 collection schema, and contain only
  placeholders ([collection](../assets/shop.postman_collection.json.template),
  [environment](../assets/local.postman_environment.json.template)).
- Detail: [collections and files](collections.md),
  [Schemathesis](schemathesis.md),
  [contracts, negative cases, and CI](contracts-negative-ci.md).

## Primary sources

- [Postman Collection Format v2.1.0 schema](https://schema.getpostman.com/json/collection/v2.1.0/collection.json)
- [Newman documentation](https://learning.postman.com/docs/collections/using-newman-cli/command-line-integration-with-newman/)
- [Bruno documentation](https://docs.usebruno.com/)
- [Schemathesis documentation](https://schemathesis.readthedocs.io/en/stable/)
- [Pact documentation](https://docs.pact.io/)
- [OWASP API Security Testing (WSTG)](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/12-API_Testing/README)
