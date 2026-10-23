# Toolchain metafiles

Metafiles are the configuration files that define what "correct" means for a
repository: formatter style, lint rules, test markers, spelling words, ignored
paths, pinned tool versions. A gate is only reproducible when these files are
explicit, versioned and owned.

## Inventory

| Concern | Typical file | Notes |
| --- | --- | --- |
| Dependencies and tool versions | `pyproject.toml` + `uv.lock` | dev tools in a dependency group so `uv run --locked` pins them |
| Formatter and linter | `ruff.toml` or `[tool.ruff]` | one place; per-file ignores carry a reason comment |
| Type checker | `mypy.ini`, `pyrightconfig.json` or `[tool.*]` | strictness flags explicit |
| Tests | `pytest.ini` or `[tool.pytest.ini_options]` | markers registered, `strict = true` (pinned pytest 9+) or `--strict-markers`, warnings policy |
| Coverage | `.coveragerc` or `[tool.coverage]` | `branch = true`, thresholds, justified excludes |
| Import contracts | `.importlinter` | layer and forbidden contracts |
| Spelling | `cspell.json` + project word list | see [spell and link checking](spell-and-link-checking.md) |
| Markdown style | `.markdownlint-cli2.yaml` | disabled rules carry a reason |
| Links | `.lychee.toml` | excludes for known-unreachable hosts, timeouts, retries |
| Secrets | `.secrets.baseline` | audited; see [secrets scanning](secrets-scanning.md) |
| Hooks | `.pre-commit-config.yaml` | pinned `rev`s, check-only defaults |
| CI | `.github/workflows/*.yml` | calls the same gate script |
| Editors | `.editorconfig`, `.vscode/settings.json` | line endings, indentation, final newline |
| Git attributes | `.gitattributes` | `* text=auto eol=lf` to stop line-ending churn |
| Task runner | `Taskfile.yml`, `Makefile`, `noxfile.py` | thin wrappers around the gate, not a second definition |

## Rules

- **One file per tool, one owner per file.** Prefer a dedicated file when a
  tool supports it and the configuration is long; `pyproject.toml` sections
  are fine for short ones. Do not configure the same tool in two places.
- **Pin versions in one place.** Python tools in the lockfile; Node tools by
  exact version in the command (`npx --yes cspell@10`); hooks by `rev`; CI
  actions by commit SHA. A floating version makes yesterday's green build red
  without a code change.
- **Explain every exception.** An ignored rule, excluded path or allowed word
  without a reason becomes permanent. Add a comment naming why and, for
  temporary ones, when to revisit.
- **Never weaken to pass.** Raising a complexity limit, lowering a coverage
  threshold or adding a broad ignore to make a gate green is a policy change
  that needs its own review, not a side effect of a feature.
- **Keep generated and vendored paths out** of every tool with the same exclude
  list, so tools agree on what is source.
- **Validate configuration files themselves**: JSON and YAML parse, schemas
  for CI workflows and dependency bots, `--strict-config` for pytest.

## Changing a metafile

1. State the intended policy change and its scope.
2. Run the affected tool on the whole repository before and after; record the
   finding counts.
3. Fix or explicitly baseline new findings in the same change.
4. Mirror the change in pre-commit and CI if they invoke the tool differently
   (they should not; see [pre-commit and CI parity](precommit-ci-parity.md)).

## Sources

- uv, [Locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- Ruff, [Configuring Ruff](https://docs.astral.sh/ruff/configuration/)
- pytest, [Configuration](https://docs.pytest.org/en/stable/reference/customize.html)
- EditorConfig, [project site](https://editorconfig.org/)
- Git, [gitattributes documentation](https://git-scm.com/docs/gitattributes)
- GitHub, [Security hardening for GitHub Actions](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions)
