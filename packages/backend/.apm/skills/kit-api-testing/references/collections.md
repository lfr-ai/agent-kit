# Collections, environments, and request files

Reviewed 2026-10-23.

## Postman and Newman

- Store collections in Collection Format v2.1
  ([template](../assets/shop.postman_collection.json.template)) and export
  them into the repository so changes are reviewed.
- Variables: collection variables for API-level constants (prefix, fixture
  identifiers); environment variables for anything that differs per
  deployment ([template](../assets/local.postman_environment.json.template)).
- Secrets: committed environment files contain empty values with
  `"type": "secret"`. CI supplies them at run time from its secret store,
  for example by writing a temporary environment file with restricted
  permissions on an ephemeral runner, or with `--env-var` on a runner whose
  process list is not shared. Never export a collection with tokens filled in.
- Put the bearer auth on the collection and override with `noauth` on
  requests that test the unauthenticated path.
- Assertions: status, media type, required keys, and headers that are part of
  the contract (`WWW-Authenticate`, `Retry-After`, `X-Request-ID`). Leave full
  schema checks to Schemathesis.
- Newman in CI:

```text
newman run shop.postman_collection.json \
  -e local.postman_environment.json \
  --reporters cli,junit --reporter-junit-export reports/newman.xml \
  --bail --timeout-request 10000
```

Pin the Newman version in the project's locked JavaScript tooling; do not
fetch it ad hoc in CI.

## Bruno

Bruno stores each request as a `.bru` text file in a folder per collection,
with environments in `environments/*.bru`. Secrets go in a git-ignored `.env`
file referenced as `{{process.env.NAME}}`. Run with `bru run --env <name>` in
CI. Choose Bruno when collections must be diffable and no cloud workspace is
allowed. Bruno can import Postman v2.1 collections.

## `.http` files

[shop.http.template](../assets/shop.http.template) works in editors that
support the format (VS Code REST Client, JetBrains HTTP Client). Use them for
manual exploration and reproducible bug reports. Variables declared with
`@name = value` are public; tokens come from the editor's private environment
file, which is git-ignored. They are not a CI test suite.

## Rules for every format

- No real hosts, tokens, personal data, or customer identifiers in committed
  files; use `example.test` and synthetic identifiers.
- Each request name states the expected outcome ("Missing token is 401").
- Requests that change data run against seeded test data and clean up after
  themselves, or run only in disposable environments.

## Primary sources

- [Postman: Collection Format v2.1 specification](https://schema.postman.com/collection/json/v2.1.0/draft-07/docs/index.html)
- [Postman: Variables](https://learning.postman.com/docs/sending-requests/variables/variables/)
- [Postman: Writing tests](https://learning.postman.com/docs/tests-and-scripts/write-scripts/test-scripts/)
- [Newman command-line options](https://learning.postman.com/docs/collections/using-newman-cli/newman-options/)
- [Bruno: Collections and environments](https://docs.usebruno.com/)
- [Bruno CLI](https://docs.usebruno.com/bru-cli/overview)
- [VS Code REST Client](https://marketplace.visualstudio.com/items?itemName=humao.rest-client)
- [JetBrains HTTP Client](https://www.jetbrains.com/help/idea/http-client-in-product-code-editor.html)
