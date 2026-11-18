# Tests

Every test lives in one tier; `tests/conftest.py` marks it from its directory.

| Tier | Path | Marker | Scope |
| --- | --- | --- | --- |
| Unit | `tests/unit/<layer>/` | `unit` | One `src/agent_kit/` layer (`core`, `application`, `infrastructure`, `composition`), in process, synthetic inputs |
| Unit, runtime | `tests/unit/runtime/` | `unit` | The `platform_kit_runtime` package under `packages/runtime/`, in process |
| Unit, delivery | `tests/unit/delivery/` | `unit` | `packages/delivery` documents, catalog, template contracts and identity guide |
| Repository guards | `tests/unit/repo_guards/` | `unit` | Contracts over this repository's real files and `scripts/` checks |
| Property | `tests/property/` | `property` | Hypothesis invariants (paths, hashing, selection) |
| Integration | `tests/integration/` | `integration` | Repository script process boundaries and composition/provenance behavior over synthetic or repository sources |
| Integration, runtime | `tests/integration/runtime/` | `integration` | Runtime facades, offline SDK/HTTP flows and the installed wheel |
| Integration, delivery | `tests/integration/delivery/` | `integration` | Imported shell gates, package relocation and the Azure bootstrap CLI |
| Integration, delivery IaC | `tests/integration/delivery/infra/` | `integration` | One `test_<module>.py` per `packages/delivery/infra/<module>`, sharing the `iac.py` harness; tool-backed cases skip when Terraform or Bicep is not installed |
| Integration, starter | `tests/integration/starter/` | `integration` | Copier generation, rendered IaC, environments, deploy pipelines and the generated service |

Unit layer folders follow the current `src/agent_kit/` layers; a layer without
unit tests has no folder. A subfolder replaces a shared file-name prefix only
when it mirrors one source area (`starter/`, `delivery/infra/`); feature tests
over a layered package, such as `runtime/`, and the cross-cutting
`repo_guards/` stay flat. `pytest.ini` puts `packages/delivery` on the import
path for `delivery_tools`. The `source_root` fixture builds a complete synthetic
source tree in `tmp_path`.

The released APM CLI boundary is exercised separately by `task apm:smoke`
([`scripts/apm_smoke.py`](../scripts/apm_smoke.py)), not by pytest. It tests
composed source-package delivery, not resolution of a published profile
dependency closure; see [compatibility](../docs/compatibility.md#package-boundaries).
Each vendor command streams its output with a 120-second deadline and closed
stdin. `task apm:smoke -- --session --timeout-seconds 90` runs one skill with an
explicit shorter deadline. Synthetic process regressions cover timeout cleanup
of a launcher and child, output streaming, stdin closure and fixture isolation;
they do not certify a native agent session.
The process-boundary tests also assert that `python -m agent_kit` has no public
entry point.
[Capability evaluation cases](evals/README.md) additionally describe observed
agent behavior; they are not pytest cases or pre-filled passing model results.

## Running

```powershell
task test                         # every tier in parallel, matching CI
task test -- tests/unit           # one tier or file, using pytest selectors
task test -- tests/unit/core -n 0 # small scope without worker startup
task test -- --lf                 # rerun failures during the current iteration
task test -- tests/integration    # process and end-to-end tier
task test -- -m "not integration and not slow"  # fast tier
task check                        # fixes, types, imports, fast unit and property
task verify -- tests              # every tier with enforced branch coverage
uv run --locked tox -e 3.14       # isolated environment for one interpreter
```

`slow` marks guards that copy or install whole profiles (capability coverage,
consumer roles, profile budgets, the CLI-template run). They stay in
`task test`, `task verify` and CI; only `task check` skips them. Mark a test
`slow` only when it costs seconds per case and an always-run gate still
executes it.

Start with the nearest proving test, not the full matrix. Parameterize only
meaningfully different contracts; reuse a module-scoped rendered fixture for
read-only assertions instead of copying the complete catalog for each case.
Keep filesystem isolation for mutation tests. Use `--durations=10` on a scoped
run before changing scheduling or declaring a test slow. A speed improvement
must preserve the same required final outcomes, not remove negative cases.

`pytest.ini` owns discovery, markers, and strictness (`strict = true` for config,
markers, unique parametrization ids, and xfail; warnings as errors). Coverage settings live
in `.coveragerc`; subprocesses started by integration tests are measured too.

Run verification, tox, and all-file hooks sequentially in a shared checkout.
Preserve the complete output of a failed run before retrying; a passing retry
does not identify the original failure. To limit local CPU use without changing
the suite, set `PYTEST_XDIST_AUTO_NUM_WORKERS=4` before an `auto` run.

## Adding a test

- Put it in the tier and layer of the behavior it proves; name files `test_*.py`.
- Assert observable behavior (exit codes, findings, written bytes), not internals.
- Add a negative case for every new validation rule.
- Keep tests deterministic: no network, no sleeps, `tmp_path` for all writes.
