# Tests

Every test lives in one tier; `tests/conftest.py` marks it from its directory.

| Tier | Path | Marker | Scope |
| --- | --- | --- | --- |
| Unit | `tests/unit/<layer>/` | `unit` | One module or layer, in process, synthetic inputs |
| Repository guards | `tests/unit/repo_guards/` | `unit` | Contracts over this repository's real files and `scripts/` checks |
| Property | `tests/property/` | `property` | Hypothesis invariants (paths, hashing, selection) |
| Integration | `tests/integration/` | `integration` | Real `python -m agent_kit` processes and end-to-end composition |

Unit folders mirror `src/agent_kit/`: `application/`, `composition/`,
`infrastructure/`, and `presentation/`. The `source_root` fixture builds a
complete synthetic source tree in `tmp_path`.

The released APM CLI boundary is exercised separately by `task apm:smoke`
(`scripts/apm_smoke.py`), not by pytest.

## Running

```powershell
task test                         # every tier in parallel, matching CI
task test -- tests/unit           # one tier or file, using pytest selectors
task test -- tests/integration    # process and end-to-end tier
task test -- -m "not integration and not slow"  # fast tier
task verify -- tests              # every tier with enforced branch coverage
uv run --locked tox -e 3.14       # isolated environment for one interpreter
```

`pytest.ini` owns discovery, markers, and strictness (`--strict-markers`,
`--strict-config`, `xfail_strict`, warnings as errors). Coverage settings live
in `.coveragerc`; subprocesses started by integration tests are measured too.

## Adding a test

- Put it in the tier and layer of the behavior it proves; name files `test_*.py`.
- Assert observable behavior (exit codes, findings, written bytes), not internals.
- Add a negative case for every new validation rule.
- Keep tests deterministic: no network, no sleeps, `tmp_path` for all writes.
