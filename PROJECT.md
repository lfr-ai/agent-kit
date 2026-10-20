# Agent Kit project facts

## Identity

- Package: `agent_kit`, Python CLI; no FastAPI or frontend application.
- Toolkit version: 0.1.0, pre-release adoption baseline.
- Package manager: uv; commit `uv.lock`. Task owns local and CI gates.
- Python: 3.13 baseline. APM CLI: `apm-cli==0.33.0` in the dev group.
- Catalog: [catalog.json](catalog.json); policy: [apm-policy.yml](apm-policy.yml).
- Repository initialization, remote ownership, branch rules, and publication are
  operator actions.
- Ownership/contact source: [.github/maintainers.json](.github/maintainers.json);
  personal owner `@lfr-ai`, intended remote `lfr-ai/agent-kit`.
  Do not use an authenticated profile as an implicit owner.

## Commands

```powershell
uv sync --locked
task verify
uv run agent-kit check --root .
uv run agent-kit compose backend --root . --output build/backend
uv run agent-kit provenance --root build/backend
task apm:smoke
```

- `task verify`: check-only formatting, lint, types, architecture, source contracts,
  every test tier with branch coverage, and docs; does not update outputs.
- `task test` runs every tier; pass pytest selectors after `--`.
  `task verify -- tests` adds branch coverage. Test tiers are described in
  [tests/README.md](tests/README.md).
- Tool configuration lives in its own file: [ruff.toml](ruff.toml), [ty.toml](ty.toml),
  [pytest.ini](pytest.ini), [.coveragerc](.coveragerc), [tox.ini](tox.ini),
  [.cz.toml](.cz.toml) (commitizen), [.yamllint.yaml](.yamllint.yaml),
  [.markdownlint-cli2.yaml](.markdownlint-cli2.yaml), [cspell.json](cspell.json),
  [lychee.toml](lychee.toml), [.jscpd.json](.jscpd.json), and
  [.secrets.baseline](.secrets.baseline) (detect-secrets).
- `task precommit`: pre-commit-stage hooks on all files (requires a git repository,
  Node.js for upstream Node hooks, Bun for duplication checks, and Docker for links).
  Link and duplication checks run at pre-commit, not a separate manual stage.
- `task commit`: Conventional Commits; `uv run --locked cz bump --dry-run --yes`
  previews the next version without changing files.
- Dependency updates: Dependabot ([.github/dependabot.yml](.github/dependabot.yml))
  for uv, GitHub Actions, and pre-commit hooks.
- `task apm:smoke`: real released APM CLI boundary in disposable packages.
- `task apm:smoke -- --session`: actual one-skill delivery with no native roles.
- `compose --skill`: explicit task procedures; `.apm/selection.json` records the
  delivered roster and character footprint without token/cost claims.
- `task format`: explicit authoring formatter; never part of the read-only audit.
- `task precommit`: checks all files after an operator initializes the repository.
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
- `task verify -- conventions`: execute the portable AST convention checker.
- Task exposes ten recurring workflows, not aliases for every executable.
  `task verify -- <gate>` selects a named gate; one-off tools use their own CLI.
  See [developer tooling](docs/devtools.md) for defaults, hooks and template guidance.

## Boundaries

- Portable source belongs to APM bundles, not runtime discovery directories.
- Native reviewers and the advisory session-entry hook are repository-specific.
- Consumer projects own their facts, knowledge, memory, secrets, and app checks.
- [projects.md](projects.md) indexes this repository; it is not a fleet inventory.
- [Hexagonal Architecture](.agents/knowledge-base/architecture.md) describes dependency direction.
- [Coverage](.agents/agentic-setup/coverage.json) tracks all original capabilities,
  including deliberate consolidation and consumer-owned exclusions.
