# Verification contract

## Local and CI parity

[scripts/verify.py](../scripts/verify.py) owns the check sequence.
[Taskfile.yml](../Taskfile.yml) and CI invoke it without sync, formatting or output
refresh. After [bootstrap](devtools.md#entry-points), run `task verify`, or
`task verify -- docs` for local documentation links. A failed gate stops the run;
fix its owning source and rerun. Pre-commit supplements, not replaces, CI.

[CI](../.github/workflows/ci.yml) requires the
[dependency audit](../.github/workflows/dependency-audit.yml) before installs.
Then `verify` (gate plus packaging), `precommit` (all hooks on Ubuntu) and
`smoke` run in parallel. Verify/smoke use Ubuntu/Windows and Python 3.13/3.14;
the coverage-upload job follows verify. The audit also runs daily.

`Required toolkit checks` always runs and requires success from every other job,
including audit and coverage upload. The committed ruleset requires only this
status; that is not hosted-enforcement evidence, and admin PR bypass skips it.
See [GitHub setup](github-setup.md#agent-access-for-the-improvement-loop).
The [governance gate](../scripts/check_governance.py) enforces job dependencies
and explicit timeouts. CI owns the uv pin; [pyproject.toml](../pyproject.toml)
owns its minimum, and [tox.ini](../tox.ini) reuses the installed uv.

| Gate | Evidence |
| --- | --- |
| Source contracts | Metadata, catalog, strict policy, links, hidden characters, budgets |
| Completeness | Original skill/rule/role inventory, replacements, exclusions, task resources |
| Resource depth | Reachable references/assets for every skill, Python resource syntax, exact implemented-script paths and both optional native MCP inventories |
| Conventions | One portable AST checker plus Ruff, types and import boundaries |
| Suppression reasons | Supported active directive comments in authored source/templates need an explanation; native tools validate directive semantics, reviewers assess the reason |
| Existing delivery drift | Explicit APM policy and native output audit before regeneration |
| Open-source governance | Ownership consistency, community entries, immutable workflow pins and narrow permissions |
| Dependency licenses | Installed distributions against the reviewed, expiring license policy |
| Version pins | Exact tool pins, frozen hook commits, image and feature digests, no package runners or unlocked installs |
| Dependency vulnerabilities | Explicit network gate: hashed lock audit and wheel-only installs before syncing; required in CI and scheduled daily |
| Release products | Exact artifact inventory, version/license alignment, independent source composition, checksums |
| Unit/property tests | Synthetic profile, collision, path, provenance, and process boundaries |
| Architecture | Declarative inward import contracts |
| Documentation | Source entry files and local links, excluding consumer templates |
| Actual APM | [Smoke selections](../scripts/apm_smoke.py) install selected source-package closures in disposable consumer projects, compile both targets, compare selected resources and replay the lock; it does not verify a published profile meta-package |
| Session context | The repository-owned hook script emits bounded advisory JSON; its native registration and interpreter are checked |
| Distribution | Build the Python wheel/sdist with the declared build backend |
| Native host | Separate live-session certification, not inferred from file or APM tests |

For capability behavior, use the [repository evaluation cases](../tests/evals/README.md)
and record observations from the relevant named host and version. The
observation checker verifies record completeness only: it does not run a model,
authenticate observations or prove model quality. Offline `task verify` checks
repository contracts, not live agent behavior.

`uv run --locked python scripts/check_governance.py --publication` additionally
requires approved ownership/private contacts. It does not certify hosted account
permissions or branch rules.

## Failure behavior

- Invalid source or policy fails before generated profile output is refreshed.
- Existing destinations and unsafe paths are never overwritten.
- Hash drift fails before installation can replace evidence.
- A process failure or timeout is not converted into success.
- Unsupported native behavior is documented and does not gain a certification label.

The deterministic gate needs the provisioned environment, not production
credentials, global setup changes, consumer projects or external resources.

For rebuilt wheels, use `uv run --no-cache --isolated --no-project --with <wheel>`
and `python -I`; isolation alone can reuse same-version cached code.
Compare installed module bytes with the archive before accepting CLI results.

`uv run --locked python -m scripts.check_resources --json` emits the per-skill
census; coverage includes that structural gate. Regressions run trusted portable
self-checks and compose the smoke matrix, comparing resource bytes and requiring
every declared role in both adapters. They execute no consumer code or MCP servers.
See the [setup walkthrough](setup-completeness.md) for consumer/host gates.

APM smoke isolates APM's user-wide lock/cache with a disposable home and consumer
project. Compilation runs per native host to preserve instruction deduplication.
Selected source and installed skills must stay byte-identical, with no injected
resources, after compilation and frozen installation. Skill trees are
excluded only from application-placement analysis, not native installation,
discovery or audit.

For simultaneous validation in a shared checkout, give coverage its own output
path, for example `$env:COVERAGE_FILE = Join-Path $env:TEMP "agent-kit-$PID.coverage"`
before `task verify`. Keep that environment for later coverage-report commands.
This isolates output files; it does not change the 90% branch-coverage gate.

Generated profile and native-role ledgers check source-to-output bytes.
Copilot prompts/Claude commands also need an authored `.apm/prompts` facade;
runtime location alone is not approval. Inspect compiled root context, lock
and ignore metadata separately with explicit APM audit. Hashes are not a
signature or authorization.

Release checks compare archives byte-for-byte with fresh trusted composition;
updating ZIP hashes cannot legitimize edits. Packaged-text changes make old
`build/` archives stale (`source archive: invalid content or license`).
The builder refuses overwrite: move/delete only identified stale archives in
`build/capabilities/*.zip` and `build/release/*.zip`, then run
`task capabilities:build -- --profile fullstack --feature iac`, then
`uv run --locked python -m scripts.check_release --tag <tag>`.
The live-verified coverage baseline fingerprints identity keys, rejecting
equal-count name substitutions.
