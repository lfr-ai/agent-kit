# Schemathesis property-based contract tests

Reviewed 2026-10-23 against the Schemathesis 4 documentation.

## What it proves

Schemathesis reads the OpenAPI description, generates valid and invalid
requests for every operation, sends them, and checks that responses stay
within the contract: no 5xx, only documented status codes and content types,
bodies that validate against their schemas, and (optionally) stateful links
between operations. It finds unhandled inputs that example-based tests miss.
It does not prove business correctness.

## In-process setup

[test_openapi_contract.py.template](../assets/test_openapi_contract.py.template)
loads the schema with `schemathesis.openapi.from_asgi("/openapi.json", app)`.
The loader runs the app's lifespan and sends requests in-process with the
host `testserver`, so:

- Build the app with test settings that serve `/openapi.json`, trust the
  `testserver` host, and use fake adapters or a disposable database.
- Provide credentials through a session-scoped fixture that mints tokens with
  local keys; function-scoped fixtures trigger a Hypothesis health check.
- Bound `max_examples` per commit; raise it in a scheduled job.

## Command-line runs against a deployment

```text
schemathesis run http://localhost:8000/openapi.json --checks all --max-examples 50
```

Run only against disposable or staging environments; generated requests
create and delete data. Configure authentication in `schemathesis.toml` with
environment-variable substitution so tokens never appear in process
arguments. Read the current CLI and configuration references before copying
flags; option names changed between major versions.

## Triage

| Failure | Usual cause | Fix |
| --- | --- | --- |
| Server error (500) | Unhandled input or missing error mapping | Validate input or map the error to a problem type |
| Undocumented status code | Handler returns 400/409/422 not listed in `responses=` | Document it or change the behavior |
| Response schema violation | Response model and schema disagree, nullable field | Fix the model; regenerate the description |
| Undocumented content type | Errors not served as `application/problem+json` in the schema | Add the shared problem response to every operation |
| Flaky failure | Shared state between generated cases | Reset fixtures per case or use stateful testing deliberately |

Reproduce a failure with the printed `curl` command or the Hypothesis seed
and add a regular regression test for it.

## Primary sources

- [Schemathesis: Testing Python apps](https://schemathesis.readthedocs.io/en/stable/guides/python-apps/)
- [Schemathesis: Python API reference](https://schemathesis.readthedocs.io/en/stable/reference/python/)
- [Schemathesis: CLI reference](https://schemathesis.readthedocs.io/en/stable/reference/cli/)
- [Schemathesis: Configuration](https://schemathesis.readthedocs.io/en/stable/reference/configuration/)
- [Schemathesis: Checks](https://schemathesis.readthedocs.io/en/stable/reference/checks/)
- [Hypothesis: Settings](https://hypothesis.readthedocs.io/en/latest/reference/api.html#settings)
- [OpenAPI Specification 3.1.1](https://spec.openapis.org/oas/v3.1.1.html)
