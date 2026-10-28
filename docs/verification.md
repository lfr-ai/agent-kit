# Verification contract

## Local and CI parity

[scripts/verify.py](../scripts/verify.py) owns the check sequence.
[Taskfile.yml](../Taskfile.yml) and the CI workflow invoke it without formatting
or refreshing generated sources. Pre-commit is supplementary, not the only CI gate.

The [CI workflow](../.github/workflows/ci.yml) first requires `audit` (the reusable
[dependency audit](../.github/workflows/dependency-audit.yml), which also runs
daily). Only after it succeeds may the dependency-consuming jobs install:
`verify` (the gate above plus packaging, on Ubuntu and Windows with Python 3.13
and 3.14), `precommit` (all hooks once on Ubuntu, with cached hook environments),
and `smoke` (real APM delivery on the same OS/Python matrix) run in parallel.
The `coverage` upload job follows `verify`.

The always-run `Required toolkit checks` summary needs all five other jobs and
requires every result to be successful, including the audit and coverage upload
job. It is the only status required by the committed branch ruleset, not proof of
hosted enforcement; the admin PR bypass also bypasses this check requirement.
See [GitHub setup](github-setup.md#agent-access-for-the-improvement-loop).
The governance gate rejects a summary that omits any other job, missing
success-only audit dependencies on the three install jobs, and any step job
without an explicit timeout. CI pins uv 0.13.3; `pyproject.toml` declares the
minimum supported uv, and `tox-uv-bare` reuses that uv instead of installing a
second copy into the environment.

| Gate | Evidence |
| --- | --- |
| Source contracts | Metadata, catalog, strict policy, links, hidden characters, budgets |
| Completeness | Original skill/rule/role inventory, replacements, exclusions, task resources |
| Resource depth | Reachable references/assets for every skill, Python resource syntax, exact implemented-script paths and both optional native MCP inventories |
| Conventions | One portable AST checker plus Ruff, types and import boundaries |
| Existing delivery drift | Explicit APM policy and native output audit before regeneration |
| Open-source governance | Ownership consistency, community entries, immutable workflow pins and narrow permissions |
| Dependency licenses | Installed distributions against the reviewed, expiring license policy |
| Version pins | Exact tool pins, frozen hook commits, image and feature digests, no package runners or unlocked installs |
| Dependency vulnerabilities | Explicit network gate: hashed lock audit and wheel-only installs before syncing; required in CI and scheduled daily |
| Release products | Exact artifact inventory, version/license alignment, independent source composition, checksums |
| Unit/property tests | Synthetic profile, collision, path, provenance, and process boundaries |
| Architecture | Declarative inward import contracts |
| Documentation | Source entry files and local links, excluding consumer templates |
| Actual APM | Three budget-compliant selections (`fullstack`; `ai` with `iac`; `workflows`) that together cover every portable bundle: install/compile, both native rosters, exact installed resource bytes, explicit policy, audit and frozen reproduction |
| Session context | Explicit allowlist, selected-skill instruction links, role omission and real narrowed APM delivery |
| Distribution | Build the Python wheel/sdist with the declared build backend |
| Native host | Separate live-session certification, not inferred from CLI tests |

`uv run --locked python scripts/check_governance.py --publication` is deliberately stricter than local verification:
unassigned approved ownership/private contacts block publication without blocking
offline development. It does not certify hosted account permissions or branch rules.

## Failure behavior

- Invalid or unknown policy fails before a composition destination is created.
- Existing destinations and unsafe paths are never overwritten.
- Hash drift fails before installation can replace evidence.
- A process failure or timeout is not converted into success.
- Unsupported native behavior is documented and does not gain a certification label.

No production credentials, global tools, existing projects, or external resources
are required for the deterministic gate.

Test rebuilt wheels with `uv run --no-cache --isolated --no-project --with <wheel>`
and `python -I` to exclude shared-cache and inherited Python-path contamination.
An isolated run alone reused older same-version wheel code during verification.
Compare installed module bytes with the new archive before accepting CLI results.

`uv run --locked python -m scripts.check_resources --json` emits the real per-skill census without generating
another authored manifest. Coverage invokes this structural gate, and tests run
trusted first-party portable checkers' isolated self-checks. The smoke-matrix
composition regression composes each smoke selection, compares original resource
bytes, and requires every one of the 27 declared roles in at least one native
roster per adapter. These checks do not execute consumer code or connect MCP servers.
See the [setup walkthrough](setup-completeness.md) for the consumer/host gates.

APM smoke uses a disposable home as well as a disposable package: the pinned CLI
holds a user-wide lifecycle lock even for different workspaces. Its source and
installed skill trees must remain byte-identical with no injected resource files,
both after compilation and after frozen installation.
Composition keeps these on-demand trees outside application placement analysis;
it does not omit their native installation or weaken audit policy.

For simultaneous validation in a shared checkout, give coverage its own output
path, for example `$env:COVERAGE_FILE = Join-Path $env:TEMP "agent-kit-$PID.coverage"`
before `task verify`. Keep that environment for later coverage-report commands.
This isolates output files; it does not change the 90% branch-coverage gate.

Provenance verifies authored source/configuration and exact first-party native
files attested in the APM ledger. Compiled root context, lock, and ignore metadata
Native prompt projections must also map to an authored `.apm/prompts` facade:
Copilot prompt files and Claude commands are not approved merely because they
occupy a runtime directory. Ledger ownership, native hashes and source hashes
remain required. Session selection omits these project-level facades. Compiled root context, lock, and ignore metadata
are not source-provenance bytes; inspect them separately and run the explicit
APM audit. The provenance file itself is not a signature or authorization grant.
Release artifacts are additionally compared byte-for-byte with fresh composition
from the trusted checkout; updating internal ZIP hashes does not legitimize a change.
Any packaged-text change makes an existing `build/` archive stale
(`source archive: invalid content or license`). The builder refuses to overwrite,
so move or delete `build/capabilities/*.zip` and `build/release/*.zip`, run
`task capabilities:build -- --profile fullstack --feature iac`, then
`uv run --locked python -m scripts.check_release --tag <tag>`.
The source coverage key set is fingerprinted from the live-verified baseline:
an equal-count name substitution is not accepted.
