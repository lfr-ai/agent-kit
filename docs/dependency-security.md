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

`task bootstrap` applies the same order on a new checkout: it installs only the
hash-locked `audit` dependency group, audits `uv.lock` and `bun.lock`, then syncs
the project, installs the locked JavaScript tools and installs Git hooks.

The `task verify` wrapper uses `uv run --locked --no-sync`, so selecting
`dependencies` cannot install a changed lock before auditing it. Audit tools must
already be provisioned; missing tools fail explicitly. The default deterministic
gate separately checks lock consistency with `uv lock --check`.

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
| Known vulnerable package | `pip-audit` on the exported, hashed `uv.lock` and `bun audit` on `bun.lock`, failing closed when a package cannot be audited | Bootstrap, lock-changing commits, required CI job, daily schedule |
| Tampered lock entry | `--require-hashes` against PyPI validates locked hashes | Same as above |
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
| Locked package vulnerabilities | pip-audit and Bun audit for their respective ecosystems | Another scanner covers an otherwise unexamined artifact |
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
| Development and audit tools | `==` in `pyproject.toml` dependency groups, hashed in `uv.lock` | Dependabot `uv` |
| Published dependency (PyYAML) | Bounded range for consumers; `uv.lock` pins the tested build | Dependabot `uv` |
| Build backend | `hatchling==1.27.0` plus `build-constraint-dependencies` for its closure | Manual review |
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
interpreter minor version is also deliberate. The build-constraint hashes that
newer uv releases support are not used until the minimum supported uv is raised;
uv 0.10 rejects that table form.

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

uv's built-in `uv audit` command and sync-time malware check are preview features
in the pinned uv line, so they are not part of the required gate.

## Vulnerability exceptions

There are no accepted vulnerabilities. If a fix is unavailable, open a tracked
issue, assess reachability, and add a time-boxed `--ignore-vuln <ID>` to the
audit command with that reference. Remove it as soon as a fixed version exists.

## Agent limits

Native permission rules match command text. They stop ordinary and
hallucination-driven installs, but a determined agent can bypass them with
another spelling, an interpreter, or a generated script. They are therefore
defense in depth, not a sandbox. For stronger isolation, enable the host's
sandbox and network allowlist where supported, run agents in the dev container,
or use managed settings. Repository rules and required checks still block an
unaudited dependency from merging.

## Residual risks

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

- [pip-audit](https://github.com/pypa/pip-audit)
- [uv settings: `exclude-newer` and `no-build`](https://docs.astral.sh/uv/reference/settings/)
- [Dependency review action](https://github.com/actions/dependency-review-action)
- [Dependabot options and cooldowns](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference)
- [Claude Code permissions](https://code.claude.com/docs/en/permissions)
- [VS Code approvals](https://code.visualstudio.com/docs/agents/run/approvals)
- [zizmor](https://docs.zizmor.sh/)
- [Self-repository workflow references](https://github.blog/changelog/2026-07-30-reference-same-repository-actions-with-self-repository-syntax/)
- [Package hallucinations by code-generating LLMs](https://arxiv.org/abs/2406.10279)
