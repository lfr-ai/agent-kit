# Dependency and agent supply-chain security

The repository treats every third-party package, hook, action, image, and
agent-initiated install as untrusted until it has passed review through a
pinned, audited path. Local controls catch mistakes early; required CI checks
and branch rules are the enforcement boundary.

## Change a Python dependency

1. Explain why the standard library or an existing dependency is insufficient.
2. Update the manifest and lock without installing anything:
   `uv add --no-sync <package>` (or edit `pyproject.toml`, then `uv lock`).
3. Audit the changed lock before syncing it:
   `task verify -- dependencies`.
4. Install the audited lock with `uv sync --locked`, then run
   `task verify -- licenses` and `task verify`.
5. Open a pull request. Dependency review checks the diff again server side.

`task bootstrap` applies the same order on a new checkout: it audits `uv.lock` and
`bun.lock` with only uv and Bun (no Python audit tool is installed), then syncs
the project, installs the locked JavaScript tools and installs Git hooks.

The audit runs
`uv audit --locked --preview-features audit-command,json-output --output-format json`.
uv queries OSV for advisories and the package index for archived, deprecated and
quarantined project statuses. The wrapper blocks every reported vulnerability
and adverse status, even when uv exits zero. It also fails closed on a nonzero
exit, missing tools, process failures, network failures surfaced by uv, unreadable
JSON, unsupported schemas, explicit errors, missing finding arrays, and
inconsistent or malformed counts (including booleans and negative numbers).
Bun runs only after Python passes. This does not guarantee a complete status scan:
uv can silently omit failed per-project status lookups; see residual risks.

The audit does not need the project environment. Bootstrap runs it with
`uv run --no-project python scripts/audit_dependencies.py`; the verification
wrapper uses `uv run --locked --no-sync`, so selecting `dependencies` cannot
install a changed lock before auditing it. The default deterministic gate
separately checks lock consistency with `uv lock --check`.

The gate requires uv `>=0.12.0,<0.14` (`required-version` in `pyproject.toml`) for
JSON reports and the selected preview-feature spelling. The command already
existed, hidden, in uv 0.10.8 and became visible in CLI help in 0.10.12.
uv 0.11.9 added adverse statuses, but status-only findings still exited zero and
JSON output was unavailable until 0.11.15. A 0.11.9 floor is therefore insufficient
for this JSON-based gate.

## Synthetic secret-scan fixtures

Deliberate negative-test inputs, environment-variable references, and
documented local-development placeholders use the pinned scanner's explicit
line annotations. This follows the existing fixture convention and keeps the
explanation with portable assets instead of requiring a checkout-specific
baseline entry. Never replace an annotated fixture with live credentials.

No detector or directory scan was disabled, and the baseline is unchanged.
Unannotated values remain scanned. Review every new finding; do not bulk-update
the baseline to make a hook pass. The hook deliberately rejects an unstaged
baseline, and protected-branch checks remain enabled for commits.

## Controls

| Risk | Control | Where it runs |
| --- | --- | --- |
| Known vulnerable or adverse-status package | `uv audit --locked` (OSV advisories plus archived, deprecated and quarantined statuses) and `bun audit` on `bun.lock`, failing closed on any finding or unreadable report | Bootstrap, lock-changing commits, required CI job, daily schedule |
| Tampered lock entry | uv verifies each locked artifact hash when `uv sync --locked` installs it; `uv audit` does not compare lock hashes with the index, so review lock diffs and keep dependency review enabled | Install, pull-request review |
| Source-only registry package | Registry packages must have wheel records; missing, empty or malformed package inventories fail before audit tools run | Same as above |
| Disallowed or unknown license | [License policy](../license-allowlist.json) evaluated by the shared license guard; unknown metadata fails unless a reviewed, expiring exception matches it | `task verify`, lock-changing commits, required CI job |
| New vulnerable or unlicensed package in a PR | Dependency review fails on any severity in runtime, development, and unknown scopes, with an SPDX allowlist | Public pull requests |
| Advisory published after merge | Scheduled dependency audit; Dependabot security updates are grouped and never delayed by cooldowns | GitHub |
| Freshly published malicious release | Dependabot cooldowns delay version updates by 14 days; zizmor enforces the minimum | GitHub, pre-commit and CI |
| Moved tags | Actions pinned to full SHAs, hook repositories frozen to commits, the link-check image pinned by digest, and same-repository workflows called with `$/` | Governance and hook regressions |
| Unsafe workflow patterns | zizmor, actionlint, and the governance gate | Pre-commit and CI |
| Hallucinated or malicious package installed by an agent | Claude Code denies literal installer and package-runner commands; VS Code always asks before them; the shared policy forbids ad-hoc installs | Native agent settings |

## Tool selection without duplicate gates

Keep one primary scanner per risk and target. Different enforcement boundaries
can reuse the same scanner: local secret checks and required CI are complementary,
not reasons to introduce another secret-scanning engine.

| Need | Existing choice | Add only when |
| --- | --- | --- |
| Committed credentials | detect-secrets with its reviewed baseline | A separate history or hosting-platform check adds coverage |
| Workflow correctness | actionlint | Another tool proves a different property |
| Workflow security | zizmor | Generic image or secret scanning does not replace this analysis |
| Locked package vulnerabilities | `uv audit` and Bun audit for their respective ecosystems | Another scanner covers an otherwise unexamined artifact |
| Dockerfile quality | Hadolint in consumer container review | A built-image scan is needed; lint does not inspect installed packages |

This toolkit does not add a general Trivy hook or duplicate its existing package
and secret audits. The portable container capability retains an opt-in,
vulnerability-only Trivy runner for actual built images, including OS packages.
Infrastructure consumers choose one configuration scanner, such as Trivy or
Checkov, rather than enabling both by default.

Release SBOM generation is deferred until a consumer, compliance rule, or
release-inventory system needs it. Lockfiles remain the installation and
dependency-audit inputs; an SBOM is a standardized release inventory, not another
scanner or a replacement for those checks. Existing build-provenance attestations
remain independent. If adopted, bind the SBOM to the released digest and distinguish
a library's tested dependency set from the versions its consumers install.

## Version pinning

Every tool that runs code is pinned, and `task verify -- pins` (also an
always-running pre-commit hook) fails on a floating reference. The portable checker
is the shared [check_pins.py](../packages/shared/.apm/skills/kit-verify-change/assets/check_pins.py).

| Surface | Pin | Updater |
| --- | --- | --- |
| Development tools | `==` in `pyproject.toml` dependency groups, hashed in `uv.lock` | Dependabot `uv` |
| Published dependency (PyYAML) | Bounded range for consumers; `uv.lock` pins the tested build | Dependabot `uv` |
| Build backend | `hatchling==1.27.0` plus `build-constraint-dependencies` for its closure | Manual review: edit both pins, run `uv lock`. Dependabot ignores it because it cannot update the lock's build constraint |
| tox provisioning | `==` matching the lock | Manual with the lock |
| JavaScript tooling | Exact `package.json` version and integrity-hashed `bun.lock`; scripts disabled | Dependabot `bun` |
| GitHub Actions | Full commit SHA with version comment; same-repository calls use `$/` | Dependabot `github-actions` |
| pre-commit hooks | Full commit SHA with `# frozen:` comment | Dependabot `pre-commit` |
| Hook toolchains | Exact `language_version` (Go `1.27.3` for actionlint) | Manual review |
| Link-check image | Tag plus `@sha256` digest | Manual review |
| Dev container base image | Digest in [.devcontainer/Dockerfile](../.devcontainer/Dockerfile) | Dependabot `docker` |
| Dev container features | Digest and integrity in `devcontainer-lock.json`; exact tool versions | Dependabot `devcontainers` |
| CI tool installers | Exact uv, Bun and Codecov CLI versions; fixed runner images | Manual review |
| Python runtime | Minor version (`3.13`, `3.14`), so CI receives interpreter security patches | GitHub runner images |

The published PyYAML range is deliberate: exact pins in package metadata would
force conflicts on consumers and stop them from receiving security fixes. The
interpreter minor version is also deliberate. Build constraints currently pin
versions, not artifact hashes; do not treat them as a second hashed lock.

Wheel records prove that a binary artifact exists, not that it matches every
interpreter/platform. The preflight is not an installer sandbox. Consumers that
require binary-only installation must verify compatible wheels and their
package-manager version's build controls, including editable first-party builds.

## Why there is no global resolver cooldown

uv's `exclude-newer` can ignore releases newer than a duration, but it also
blocks a security fix published the same week and prevents Dependabot security
updates from resolving it. The repository therefore keeps cooldowns on Dependabot
version updates only. Use `uv lock --exclude-newer "14 days"` for an individual
manual update when a fix is not urgent.

Every configured ecosystem uses `cooldown.default-days: 14`; major, minor and
patch releases inherit it without shorter overrides. The zizmor policy and APM
templates use the same minimum. Cooldown controls release age, not the polling
schedule: with weekly checks, a version update may be proposed later than day 14.
GitHub excludes security updates from cooldowns.

uv's `uv audit` command is still classified as a preview feature by Astral, so the
gate passes `--preview-features audit-command,json-output` explicitly and the
`required-version` floor guards the behavior it relies on. The sync-time malware
check remains outside the required gate.

## Vulnerability exceptions

There are no accepted vulnerabilities. If a fix is unavailable, open a tracked
issue, assess reachability, and obtain approval for a time-boxed exception.
An operator can then explicitly pass
`uv run --no-project python scripts/audit_dependencies.py --ignore-until-fixed <ID>`
(repeat the option for multiple IDs). The wrapper forwards these IDs to uv;
uv stops ignoring an advisory as soon as a fixed version exists. No advisory is
ignored by default, and this option does not exempt adverse project statuses.
An exceptional run does not change the required gate's policy; any standing
exception needs a separately reviewed policy change and tracked expiry.

## Agent limits

Native permission rules match command text. They stop ordinary and
hallucination-driven installs, but a determined agent can bypass them with
another spelling, an interpreter, or a generated script. They are therefore
defense in depth, not a sandbox. For stronger isolation, enable the host's
sandbox and network allowlist where supported, run agents in the dev container,
or use managed settings. Repository rules and required checks still block an
unaudited dependency from merging.

## Residual risks

- uv's project-status audit drops per-project lookup and status-deserialization
  failures at trace level, including network and not-found errors. This behavior
  is present in 0.11.9, the tested 0.12.5, and current upstream source. Such failures
  do not appear in the JSON report and cannot be distinguished from a clean
  status scan by this wrapper. Fully fail-closed status coverage needs an upstream
  strict/error-reporting mode or a separately approved control; parsing trace logs
  is not a stable security contract.
- Upstream pre-commit hook environments (for example detect-secrets, cspell and
  markdownlint) install their own dependencies from the frozen hook commit; their
  transitive versions are resolved by pre-commit, not by this repository's locks.
- The Codecov upload relies on a third-party service; it receives only the
  coverage XML and is non-blocking.
- License evidence comes from installed metadata, which can be wrong; exceptions
  record the reviewed license file and expire.
- Dependency review requires a public repository or GitHub Advanced Security.
- Hosted settings such as secret-scanning push protection, private vulnerability
  reporting, Dependabot security updates, immutable releases, and rulesets must
  be enabled by the repository owner; see [GitHub setup](github-setup.md).

## Sources

- [uv audit CLI reference](https://docs.astral.sh/uv/reference/cli/#uv-audit)
- [uv preview features](https://docs.astral.sh/uv/concepts/preview/#audit-command)
- [uv 0.10.8 hidden audit command](https://github.com/astral-sh/uv/blob/0.10.8/crates/uv-cli/src/lib.rs)
- [uv 0.10.12: audit shown in CLI help](https://github.com/astral-sh/uv/releases/tag/0.10.12)
- [uv 0.11.9: adverse project statuses](https://github.com/astral-sh/uv/releases/tag/0.11.9)
- [uv 0.11.9 audit exit behavior](https://github.com/astral-sh/uv/blob/0.11.9/crates/uv/src/commands/project/audit.rs)
- [uv 0.11.15: JSON audit output](https://github.com/astral-sh/uv/releases/tag/0.11.15)
- [uv 0.12.0 preview feature names](https://github.com/astral-sh/uv/blob/0.12.0/crates/uv-preview/src/lib.rs)
- [uv 0.12.5 JSON audit schema](https://github.com/astral-sh/uv/blob/0.12.5/crates/uv/src/commands/project/audit/json.rs)
- [uv 0.12.5 status lookup error handling](https://github.com/astral-sh/uv/blob/0.12.5/crates/uv-audit/src/service/project_status.rs)
- [Current upstream status lookup error handling](https://github.com/astral-sh/uv/blob/main/crates/uv-audit/src/service/project_status.rs)
- [uv settings: `exclude-newer` and `no-build`](https://docs.astral.sh/uv/reference/settings/)
- [Dependency review action](https://github.com/actions/dependency-review-action)
- [Dependabot options and cooldowns](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference)
- [Claude Code permissions](https://code.claude.com/docs/en/permissions)
- [VS Code approvals](https://code.visualstudio.com/docs/agents/run/approvals)
- [zizmor](https://docs.zizmor.sh/)
- [Self-repository workflow references](https://github.blog/changelog/2026-07-30-reference-same-repository-actions-with-self-repository-syntax/)
- [Package hallucinations by code-generating LLMs](https://arxiv.org/abs/2406.10279)
