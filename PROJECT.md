# Agent Kit project facts

## Identity

- Package: `agent_kit`, Python maintainer tooling; consumers install APM profiles
  and do not need an Agent Kit Python package or executable.
- Toolkit version: 0.1.0, pre-release adoption baseline.
- Package manager: uv; commit `uv.lock`. Task owns local and CI gates.
- Python: 3.13 baseline. Maintainer APM CLI: `apm-cli==0.33.0` in the dev group.
- Agent Kit's own CLI is retired. The internal
  [APM adapter](src/agent_kit/infrastructure/apm_adapter.py) invokes Microsoft's
  external `apm` executable for maintainer policy and audit checks; it is not
  an Agent Kit command-line entry point.
- Profile source: [catalog.json](catalog.json); generated APM meta-package
  manifests: described in [the profile guide](.agents/agentic-setup/profiles.md);
  policy: [apm-policy.yml](apm-policy.yml).
- Repository initialization, remote ownership, branch rules, and publication are
  operator actions.
- Ownership/contact source: [.github/maintainers.json](.github/maintainers.json);
  owner `@lfr-ai`, public repository `lfr-ai/agent-kit` on `main`.

## Commands

```powershell
task bootstrap
task verify
task profiles:build
task apm:smoke
```

- `task verify`: check-only lock consistency, formatting, lint, types, architecture, source contracts,
  dependency licenses, every test tier with branch coverage, and docs; does not
  update outputs, synchronize dependencies or require network access. Provision
  the reviewed environment with `task bootstrap` first.
- `task verify -- dependencies`: network audit of the locked dependencies before
  installation. `task verify -- pins` rejects floating versions, mutable hook
  revisions, undigested images and package runners. See
  [dependency security](docs/dependency-security.md).
- `task verify -- source` runs [`scripts/check_source.py`](scripts/check_source.py)
  to validate the canonical catalog and package sources. This is maintainer
  tooling; consumers install a profile through APM.
- `task profiles:build`: regenerate compact APM profile manifests from
  `catalog.json` and the canonical `packages/*/apm.yml` manifests. Consumers do
  not run this task.
- `task bootstrap` needs uv and Bun: it audits `uv.lock` and `bun.lock`, installs
  both locked environments, then installs Git hooks.
  Task children default `AGENT_KIT_DIR` to the actual checkout root unless the
  caller already set it. On Windows,
  bootstrap also registers it in the user environment for future processes;
  `task checkout:register` repeats that step after moving the clone.
  Fully restart VS Code and terminals to inherit the persisted value.
- `task test` runs every tier; pass pytest selectors after `--`.
  `task verify -- tests` adds branch coverage. Test tiers are described in
  [tests/README.md](tests/README.md).
- `task test:matrix` runs the locked tox Python 3.13/3.14 and coverage
  environments sequentially; use `-- -e unit` for one environment. Do not run
  it concurrently with `task verify`, which writes the same coverage reports.
- Tool configuration lives in its own file: [ruff.toml](ruff.toml), [ty.toml](ty.toml),
  [pytest.ini](pytest.ini), [.coveragerc](.coveragerc), [tox.ini](tox.ini),
  [.cz.toml](.cz.toml) (commitizen), [.yamllint.yaml](.yamllint.yaml),
  [.markdownlint-cli2.yaml](.markdownlint-cli2.yaml), [cspell.json](cspell.json),
  [lychee.toml](lychee.toml), [.jscpd.json](.jscpd.json),
  [package.json](package.json) with [bun.lock](bun.lock) and
  [bunfig.toml](bunfig.toml) (locked JavaScript tooling), and
  [.secrets.baseline](.secrets.baseline) (detect-secrets).
- `task precommit`: pre-commit-stage hooks on all files (requires a git repository,
  Node.js for upstream Node hooks, Bun for duplication checks, and Docker for links).
  Link and duplication checks run at pre-commit, not a separate manual stage.
- `task commit`: Conventional Commits; `uv run --locked cz bump --dry-run --yes`
  previews the next version without changing files.
- `task version:preview` also previews generated changelog notes.
  `task version:prepare` updates version metadata and the lock after confirmation;
  it never commits, tags or overwrites the curated changelog.
- `task release:build` builds and verifies the exact release products.
  `task release:publish TAG=v0.1.1` is an operator-only, confirmed publication
  of an existing GitHub draft; see [releasing](docs/releasing.md).
- Dependency updates: Dependabot ([.github/dependabot.yml](.github/dependabot.yml))
  for uv, Bun, GitHub Actions, pre-commit hooks, the dev container image, and
  dev container features.
- `task apm:smoke`: released APM CLI install/compile, audit and frozen-replay
  checks for composed source packages in disposable projects. It does not
  certify resolution of a published profile's dependency closure; see
  [compatibility](docs/compatibility.md).
- Repository-owned [capability evaluation cases](tests/evals/README.md) define
  synthetic tasks and a result format; cases are not observed passes. The
  checker validates record completeness only: it neither runs a model nor
  authenticates observations. Behavior claims require actual runs in a named
  host and version; structural and packaging checks are not live certification.
- `task apm:smoke -- --session`: actual one-skill delivery with no native roles.
- A consumer pins one generated profile meta-package in its root `apm.yml`; APM
  resolves its pinned source-package closure and owns installation, compilation,
  lockfiles, and installed-file audits.
  See the [consumer walkthrough](docs/setup-completeness.md).
- `task format`: explicit authoring formatter; never part of the read-only audit.
- `task verify -- governance`: community, ownership consistency, and workflow safety.
- `uv run --locked python scripts/check_governance.py --publication`: enforce
  personal ownership/private-contact consistency.
- `uv run --locked python -m scripts.check_release`: inspect built products,
  version/license alignment, and checksums.
- `task verify -- coverage`: original inventory, source replacements, template syntax.
- `uv run --locked python -m scripts.check_resources --json`: linked per-skill reference/asset/script census;
  structural resource depth, not semantic or live-runtime certification.
- `uv run --locked python .agents/guard/verify_agent_config.py`: relocation-safe
  facade for configuration-only gates; `task verify` already includes these checks.
- [VS Code setup](docs/editor.md): workspace-local editor, interpreter, task,
  debugging and customization contracts; no user-global settings are installed.
- Hosted review templates are [.codecov.yml](.codecov.yml) and
  [.coderabbit.yaml](.coderabbit.yaml); they do not install or activate either
  hosted service. See [GitHub setup](docs/github-setup.md).
- `task verify -- conventions`: shared AST checker for toolkit Python rules and
  named numeric values and double-backtick docstrings across the toolkit,
  portable assets, and production Python templates; the same script runs in
  the always-on pre-commit hook.
- `task verify -- suppressions`: checks active suppression comments in authored
  source and templates for explanatory reasons; the same checker runs in
  pre-commit. Reviewers assess the justification, and native tools still own
  directive validity and stale-suppression diagnostics.
- Task exposes recurring workflows plus a `default` target that lists them,
  not aliases for every maintainer script.
  `task verify -- <gate>` selects a named gate; one-off maintainer tools use
  their own Python entry point.
  See [developer tooling](docs/devtools.md) for defaults, hooks and template guidance.

## Boundaries

- Portable source belongs to APM bundles, not runtime discovery directories.
- Native reviewers and the advisory session-entry hook are repository-specific.
- Consumer projects own their facts, knowledge, memory, secrets, and app checks.
- [projects.md](projects.md) indexes this repository; it is not a fleet inventory.
- [Hexagonal Architecture](.agents/knowledge-base/architecture.md) describes dependency direction.
- [Coverage](.agents/agentic-setup/coverage.json) tracks all original capabilities,
  including deliberate consolidation and consumer-owned exclusions.
