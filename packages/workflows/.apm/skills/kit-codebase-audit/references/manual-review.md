# Manual review lenses

Tools find patterns; people find wrong boundaries, misleading names and
missing tests. Apply each lens to the hot spots (high churn and high
complexity), the entry points and one representative module per layer, not to
every file. Record each observation with `path:line` and grade it with
[the severity rubric](severity-rubric.md).

## Lenses

| Lens | Look for | Evidence | Owner skill |
| --- | --- | --- | --- |
| Architecture and dependency direction | inner layers importing frameworks, adapters or presentation; cycles; a composition root that is not the only place adapters are built | import-linter result, import graph, `path:line` of the import | `kit-hexagonal-architecture`, `kit-graph-analysis` |
| Ports versus adapters | ports named after technology (`PostgresRepo` as a port), adapters without a port, port signatures that leak wire types | port and adapter definitions; `check_ports_adapters.py` from `kit-hexagonal-architecture` | `kit-hexagonal-architecture` |
| Naming consistency | module file names that do not match their main class, mixed `*Service`/`*Manager` suffixes for one role, inconsistent terms across layers | `check_class_file_naming.py` and `check_naming.py` from `kit-consistency`; a term table | `kit-consistency` |
| Magic numbers | unnamed numeric literals in production code (timeouts, sizes, retries, status codes) | `check_python.py --magic-numbers` from `kit-python-service`; Ruff `PLR2004` | `kit-python-service` |
| Docstrings | public modules, classes and functions without docstrings, missing `Args`/`Returns`/`Raises`, stale descriptions | Ruff `D` rules; reading two public modules per layer | `kit-python-service`, `kit-documentation` |
| Error handling | broad `except`, swallowed errors, lost causes (no `from`), exceptions used for control flow, transport errors raised from domain code | Ruff `BLE`, `TRY`, `B904`; reading error paths of entry points | `kit-python-service` |
| Logging | `print` diagnostics, root-logger calls, eager string formatting, the same error logged at several layers, secrets or personal data in messages | Ruff `T20`, `LOG`, `G`; search for `password`, `token`, `secret` near log calls | `kit-python-service` |
| Configuration | settings read in many modules, environment variables read at import time, untyped configuration, secrets with defaults | search for `os.environ`/`getenv`; one settings object or many | `kit-config` (backend profile), `kit-python-service` |
| Tests by tier | unit tests that touch network or disk, missing integration tests at boundaries, no regression for documented errors, skipped or flaky tests | test tree per tier, markers, skip reasons, coverage by package | `kit-test-first`, `kit-verify-change` |
| Duplication and over-engineering | repeated knowledge, one-implementation interfaces without a test double, unused options | jscpd summary; call-site counts | `kit-duplication-review`, `kit-simplify-review` |
| Modernization debt | unsupported Python versions, legacy typing, abandoned packages, `setup.py` only builds | `check_legacy_syntax.py` and the ledger from `kit-modernize` | `kit-modernize` |
| Documentation | README commands that fail, architecture docs that contradict the import graph, missing contributor or security guidance | run the documented commands; compare docs with contracts | `kit-documentation` |

## How to sample

1. Rank files by churn times complexity (see the complexity reference in
   `kit-refactor`) and take the top ten.
2. Add every entry point from the inventory and one module per layer.
3. Apply all lenses to that sample; extend to more files only when a lens finds
   a pattern that may be systemic, and then count it with a search.

## Recording a manual finding

Use one line per instance while reading, then collapse:

```text
src/orders/service.py:88 | error handling | except Exception swallows PaymentDeclined; caller retries forever | high | medium | kit-python-service
```

A systemic finding states the pattern, the count, the search that produced the
count and three representative locations.

## Anti-patterns

- Reporting taste ("I would name this differently") without a project rule or
  a concrete cost.
- Reading only the newest code; old hot spots carry most of the risk.
- Treating a missing abstraction as a defect without a second variant or a test
  that needs it.
- Duplicating a tool finding as a manual one.
