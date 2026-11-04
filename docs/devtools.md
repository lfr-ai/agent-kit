# Developer tooling

Task runs recurring workflows, `task verify -- <gate>` runs one check, and the
owning CLI handles one-off work. Prerequisites: [contributing](../CONTRIBUTING.md).

## Entry points

| Need | Command |
| --- | --- |
| List targets | `task` |
| Audit locks, install Python/Bun environments and hooks | `task bootstrap` |
| Full read-only gate, including coverage | `task verify` |
| One gate (source, drift, roles, docs, ...) | `task verify -- source` |
| Locked dependency vulnerabilities (network) | `task verify -- dependencies` |
| Exact versions, frozen hooks, image digests | `task verify -- pins` |
| Python conventions, named numbers, docstrings | `task verify -- conventions` |
| Explanations for active suppression comments | `task verify -- suppressions` |
| Tests, or a pytest selector | `task test`, `task test -- tests/integration` |
| Fast subset | `task test -- -m "not integration and not slow"` |
| tox Python matrix and coverage | `task test:matrix`, `task test:matrix -- -e unit` |
| Format, lint, types | `task format`, `task lint`, `task typecheck` |
| All pre-commit-stage hooks | `task precommit` |
| Conventional Commit | `task commit` |
| Version and changelog preview / preparation | `task version:preview`, `task version:prepare` |
| Release products / operator publication | `task release:build`, `task release:publish TAG=v0.1.1` |
| Real APM delivery | `task apm:smoke` |
| Capability source archive | `task capabilities:build -- --profile fullstack` |
| Re-register the clone path on Windows | `task checkout:register` |

One-off commands, not Task targets:

```powershell
uv run --locked --no-sync python scripts/verify.py --help
uv run --locked python -m scripts.check_resources --json
uv run --locked python -m scripts.render_native --write
uv run --locked pre-commit run jscpd --all-files
```

Notes:

- The [Taskfile](../Taskfile.yml) owns targets; [editor tasks](editor.md#start)
  wrap recurring ones. Do not add a target per executable.
- MCP pins in `apm.yml` are checked by `task verify -- source`; Dependabot
  cannot bump them.
- The verifier never syncs dependencies; a stale lock or missing tool fails.
  See the [verification contract](verification.md).
- Do not run `task test:matrix` alongside another coverage gate: they share
  report paths. Test tiers: [tests/README.md](../tests/README.md).
- `AGENT_KIT_DIR` handling: see [improve the kit](feedback.md#change-a-capability).
- [check_conventions.py](../scripts/check_conventions.py) owns the AST gate
  (`--templates --only magic-number` for templates). Name nontrivial numbers;
  `0`, `1`, `-1`, annotations and test expectations are exempt. Docstrings use
  double-backtick literals; Markdown uses single backticks.

## Hooks and runtimes

[.pre-commit-config.yaml](../.pre-commit-config.yaml) owns hook order, frozen
SHAs, image digests and stages: **pre-commit** by default, **commit-msg** for
Commitizen, no manual stage. Changed locks are audited before hooks sync; see
[dependency security](dependency-security.md).

| Requirement | Detail |
| --- | --- |
| Node.js | Needed for upstream Node hooks managed by pre-commit |
| Bun | Runs locked jscpd with `bun run --bun jscpd`; bootstrap uses `bun install --frozen-lockfile`; [bunfig.toml](../bunfig.toml) disables lifecycle scripts; CI's pin is in [ci.yml](../.github/workflows/ci.yml) |
| Docker engine | Needed by the `lychee-docker` link hook; Container Tools does not provide it |
| Network | Link checks; jscpd scans the whole repository |

On Windows, if hooks ignore `SKIP`, run `Get-Command uv -All`: a version-manager
shim may alter child environments. Use the native `uv.exe` or put its directory
first on that terminal's `PATH`; do not rewrite user-global shims.

Generated capabilities, native agents and locks still get read-only checks; only
the four whitespace/newline/line-ending/BOM fixers exclude owned outputs. Fix
canonical source and regenerate with its owner; never edit attested output.

## Defaults and intentional overrides

- Large-file and branch checks keep their defaults (500 kB, `main`/`master`).
- yamllint, Import Linter and CSpell use native discovery. Hook `args` replace
  upstream arguments: a CSpell override of only `--cache` would drop
  `--gitignore --files`.
- jscpd reads [.jscpd.json](../.jscpd.json); lychee reads [lychee.toml](../lychee.toml).
  Lychee's hook manifest names an older image; review both on updates.
- [ruff.toml](../ruff.toml) owns Python target, formatter, complexity and lint
  limits. Use postponed annotations, stream writes instead of `print`, and
  stdlib-only PEP 723 asset scripts (`dependencies = []`). `T201` and `INP001`
  have no source exemption.
- Other tool settings live in the [owning configurations](../PROJECT.md#commands).
- `--locked`, read-only format checks, LF normalization, explicit secret
  baselines, stage restrictions, pins and least-privilege permissions are
  policy; do not remove them to shorten a command.

Lychee accepts HTTP 403/429, so success does not prove content. The offline docs
gate checks local files, not external links or anchors.

### Exceptions must explain intent

Every active suppression needs a short, specific reason. Name the narrow rule
and explain why it does not apply; a rule code or “reviewed exception” is not a
reason. Remove obsolete suppressions rather than justifying them after the fact.
The [suppression gate](../scripts/check_suppressions.py) runs in `task verify`
and the always-on pre-commit hooks. It checks authored code and templates,
not dependencies or generated projections. It validates the presence of a
reason; reviewers still decide whether the exception is justified.
Keep reasons in the directive only when the tool supports trailing prose.
For directives whose tail is parsed as rule names or ignored words (for example
CSpell, yamllint and hadolint), use a separate preceding comment.
Test skips and expected failures need their native `reason`; they must not hide
a failed required acceptance check. Ruff checks unused `noqa` directives too.

Configuration exclusions follow the same rule. JSON cannot carry comments, so
the rationale for the existing JSON settings is recorded here:

| Configuration | Exception and reason |
| --- | --- |
| [cspell.json](../cspell.json) | Dictionaries, generated projections, locks, reports and dependencies are not authored prose. Regexes skip content hashes, color codes, Unicode/URL escapes and literal newline/tab escapes, not ordinary words. |
| [.jscpd.json](../.jscpd.json) | Dependencies, caches, reports and generated adapters duplicate external or canonical code; check authored Python instead. Minimum lines/tokens filter trivial syntax; the percentage threshold still fails substantial duplication. |
| [ty.toml](../ty.toml) | Caches, environments and build/install output are not independent source roots; `src`, tests, scripts, guards and portable package Python remain checked. |
| [.coveragerc](../.coveragerc) | Typing-only branches, launch guards and abstract placeholders are excluded; executable implementations and CLI behavior remain test obligations. |
| [.coderabbit.yaml](../.coderabbit.yaml) | Review canonical source rather than generated projections or machine-written locks; Ruff replaces overlapping Flake8/Pylint feedback. Hosted configuration is not proof the service is active. |

[Source selection](../src/agent_kit/infrastructure/catalog_adapter.py) prunes
bytecode, Git internals, Node dependencies and caches; such files in composed
output still fail provenance. The [APM adapter](../src/agent_kit/infrastructure/apm_adapter.py)
times out at 900 seconds by default and [smoke](../scripts/apm_smoke.py) at 1800;
both use the pinned environment's APM launcher. Nonzero exits and timeouts fail.

## Scanner configuration discovery

A committed configuration does not prove a hosted scanner reads it.

| Tool | Native CLI / pre-commit | CodeRabbit |
| --- | --- | --- |
| Ruff | Closest `ruff.toml`, `.ruff.toml` or `pyproject.toml` | Same hierarchy |
| ty | [ty.toml](../ty.toml): source, scripts, tests, guard, `packages` | None; CI checks types |
| actionlint | Hook arguments here; supports standard config discovery | Default configuration only |
| zizmor | `.github/zizmor.yml`, `.github/zizmor.yaml`, `zizmor.yml`, `zizmor.yaml` | Same list |
| Gitleaks / Betterleaks | `--config`, `GITLEAKS_CONFIG`, `GITLEAKS_CONFIG_TOML`, then `.gitleaks.toml` | `gitleaks` key runs Betterleaks with bundled defaults |
| OSV-Scanner | `osv-scanner.toml` beside each scanned file; `--config` overrides | Uses repository `osv-scanner.toml` |
| detect-secrets | `--baseline .secrets.baseline` passed explicitly | None |

- zizmor policies only set a 14-day Dependabot cooldown. actionlint's `-ignore`
  covers only the unsupported `$/` workflow-call diagnostic; remove it when supported.
- Do not add empty Gitleaks/OSV suppression files without a reviewed exception.
- Hosted checks are advisory and may skip or use other versions.
- Run `ty check` at the root; `ty check packages` finding no files is not evidence.

Sources: [CodeRabbit tools](https://docs.coderabbit.ai/tools/index),
[LanguageTool](https://docs.coderabbit.ai/tools/languagetool),
[Betterleaks](https://docs.coderabbit.ai/tools/gitleaks),
[hosted zizmor](https://docs.coderabbit.ai/tools/zizmor),
[hosted actionlint](https://docs.coderabbit.ai/tools/actionlint),
[zizmor discovery](https://docs.zizmor.sh/configuration/),
[actionlint configuration](https://github.com/rhysd/actionlint/blob/v1.7.12/docs/config.md),
[OSV configuration](https://google.github.io/osv-scanner/configuration/),
[Gitleaks configuration](https://github.com/gitleaks/gitleaks#configuration),
[detect-secrets](https://github.com/Yelp/detect-secrets).

## Python exception contracts

`TRY003` and `TRY004` have no exemptions: exception classes own messages; do not
bypass them with `noqa` or message variables. Wrong types raise `TypeError`,
invalid values `ValueError`. [InputTypeError](../src/agent_kit/core/errors.py)
marks expected input failures: validation reports a finding and the CLI exits 1.
Portable scripts own local exceptions and import nothing from the toolkit.
See [TRY003](https://docs.astral.sh/ruff/rules/raise-vanilla-args/),
[TRY004](https://docs.astral.sh/ruff/rules/type-check-without-type-error/) and
[TypeError](https://docs.python.org/3/library/exceptions.html#TypeError).

## JSON and VS Code

The [editor contract](editor.md#workspace-contract) owns recognized filenames.
Keep strict **.vscode/settings.json** with `check-json` and no exclusions;
renaming to **settings.jsonc** breaks discovery.

## Future Copier templates

This repository is not yet a Copier template. When one is built: render only
selected workflows and toolchains; keep Task small and Bun/Node/Python pinned;
keep recognized editor filenames; review trust before executable tasks and never
auto-enable them; test fresh renders and updates in disposable projects.

## Primary references

- [Ruff print rule](https://docs.astral.sh/ruff/rules/print/)
- [uv scripts](https://docs.astral.sh/uv/guides/scripts/)
- [pre-commit](https://pre-commit.com/), [hooks v6.0.0](https://github.com/pre-commit/pre-commit-hooks/tree/v6.0.0), [identify](https://github.com/pre-commit/identify)
- [CSpell hook manifest v10.3.0](https://github.com/streetsidesoftware/cspell-cli/blob/v10.3.0/.pre-commit-hooks.yaml)
- [Bun run](https://bun.sh/docs/cli/run), [Bun lockfile](https://bun.sh/docs/install/lockfile), [setup-bun](https://github.com/oven-sh/setup-bun/tree/v2.2.0)
- [jscpd](https://github.com/kucherenko/jscpd/tree/v5.4.1), [lychee configuration](https://github.com/lycheeverse/lychee/blob/lychee-v0.24.2/lychee.example.toml), [yamllint](https://yamllint.readthedocs.io/en/stable/configuration.html)
- [VS Code settings](https://code.visualstudio.com/docs/configure/settings), [JSON and JSONC](https://code.visualstudio.com/docs/languages/json)
- [Task style guide](https://taskfile.dev/docs/styleguide)
- [Copier updates](https://copier.readthedocs.io/en/stable/updating/), [trusted tasks](https://copier.readthedocs.io/en/stable/configuring/#tasks)
