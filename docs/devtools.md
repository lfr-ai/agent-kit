# Developer tooling

Use Task for recurring workflows, `task verify -- <gate>` for focused checks,
and the owning CLI for one-off work. Prerequisites: [contributing](../CONTRIBUTING.md).

## Entry points

| Need | Command |
| --- | --- |
| List the targets and their descriptions | `task` |
| Audit both locks, install Python/Bun environments and Git hooks | `task bootstrap` |
| Full read-only repository gate, including coverage | `task verify` |
| One gate, such as source, drift, roles or docs | `task verify -- source` |
| Locked dependency vulnerabilities (network) | `task verify -- dependencies` |
| Exact versions, frozen hooks and image digests | `task verify -- pins` (MCP pins in `apm.yml` are checked by `task verify -- source`; Dependabot cannot bump them) |
| All tests, or a pytest selector | `task test`, `task test -- tests/integration` |
| Isolated Python versions and coverage through tox | `task test:matrix`, `task test:matrix -- -e unit` |
| Refresh the clone path for future Windows sessions | `task checkout:register` |
| Format, lint or types | `task format`, `task lint`, `task typecheck` |
| Python conventions, named numbers and docstrings | `task verify -- conventions` |
| All pre-commit-stage hooks | `task precommit` |
| Conventional Commit authoring | `task commit` |
| Read-only version and changelog preview | `task version:preview` |
| Confirmed version/lock preparation, without a commit or tag | `task version:prepare` |
| Build/check release products | `task release:build` |
| Operator-only publication of an existing draft | `task release:publish TAG=v0.1.1` |
| Real APM delivery | `task apm:smoke` |
| Capability source archive | `task capabilities:build -- --profile fullstack` |

Run `uv run --locked --no-sync python scripts/verify.py --help` to list gate names.
Use `uv run --locked python -m scripts.check_resources --json` for the resource
census, `uv run --locked python -m scripts.render_native --write` for an
approved native-role refresh, and the release guide for publication commands.
These are explicit operations, not additional aliases in Task or the editor.

The [Taskfile](../Taskfile.yml) owns targets and prerequisites;
[editor tasks](editor.md#start) wrap recurring workflows. Do not add a target
for every executable. Consumer templates live in `kit-verify-change`.

Task defaults `AGENT_KIT_DIR` to this checkout unless already set. Windows
bootstrap also registers it for future processes; use `task checkout:register`
after moving the clone, then restart the parent editor/terminal. Registration
neither installs a hook nor grants permission.

The verifier never syncs dependencies, even for the network audit. Bootstrap
first; a stale lock or missing tool fails rather than installing or repairing it.
See the [verification contract](verification.md) for evidence and failure behavior.

For a fast subset: `task test -- -m "not integration and not slow"`.
Full coverage remains in `task verify`; hooks do not replace it.
The tox matrix runs sequentially but shares report paths: do not run it alongside
another test/coverage gate. See [test tiers](../tests/README.md).

[check_conventions.py](../scripts/check_conventions.py) owns the shared AST gate,
including `--templates --only magic-number`. Name nontrivial numeric values by
intent/units; `0`, `1`, `-1`, annotations and test expectations are exempt.
Production templates are checked; test templates retain fixture literals.
Python docstrings use paired double-backtick reStructuredText literals;
Markdown uses single backticks. The gate runs on every pre-commit invocation.

## Hooks and runtimes

Run bootstrap after operator-owned repository initialization.
[.pre-commit-config.yaml](../.pre-commit-config.yaml) owns hook order, frozen SHAs,
image digests and stage selection: **pre-commit** by default, **commit-msg** for
Commitizen only, no manual stage. Changed dependency locks are audited before
syncing hooks and license checks; see [dependency security](dependency-security.md).

On Windows, check `Get-Command uv -All` if hooks ignore `SKIP`: a version-manager
shim can change child environment variables. Invoke the native `uv.exe` or put
its directory first on that terminal's `PATH`. Do not rewrite user-global shims
as a repository repair.

Pre-commit manages upstream Python/Node hook environments; Node.js is still
required. Bun runs locked jscpd with `bun run --bun jscpd`, not its Node shebang.
Bootstrap uses `bun install --frozen-lockfile`;
[bunfig.toml](../bunfig.toml) disables dependency lifecycle scripts.
Missing `node_modules` fails instead of downloading. CI's exercised Bun pin
lives in [ci.yml](../.github/workflows/ci.yml), not a latest-version promise.

Links run during commits and need network access and a running Docker engine;
the Container Tools extension does not provide that engine. The hook ID is
`lychee-docker`, not `lychee`. Duplication scans the repository once, not only
changed files. Run it alone with
`uv run --locked pre-commit run jscpd --all-files`. Failures/timeouts remain failures.

Generated capabilities, native agents and locks still receive read-only safety
checks. Only the four whitespace/newline/line-ending/BOM fixers exclude owned
outputs through the shared YAML anchor. Fix canonical source and regenerate with
its owner; never edit attested output to pass drift or native-role checks.
Lock-only changes still reach `uv lock --check`.

## Defaults and intentional overrides

- Large-file/branch checks inherit 500 kB and `main`/`master` defaults.
- yamllint, Import Linter and CSpell use native discovery/default arguments.
  Hook `args` replace rather than append upstream arguments: a CSpell override
  containing only `--cache` would lose `--gitignore --files`.
- jscpd discovers [.jscpd.json](../.jscpd.json); lychee reads
  [lychee.toml](../lychee.toml). Nonstandard filenames would require explicit
  configuration arguments.
- Lychee's pinned hook manifest names an older image; the explicit image entry
  matches the hook release. Review both together on updates.
- [ruff.toml](../ruff.toml) owns Python target, formatter, complexity and lint
  limits; portable assets have no complexity exemption. Use postponed annotations,
  stream writes instead of `print`, and stdlib-only PEP 723 asset scripts declaring
  Python 3.13 and `dependencies = []`. `T201` and `INP001` have no source exemption.
  Run environment inspection with the target environment's Python, not isolation.
- Commitizen, coverage, Markdown and YAML settings live in the
  [owning configurations](../PROJECT.md#commands); do not duplicate defaults.
- `--locked`, read-only format checks, LF normalization, test filename style,
  explicit secret baselines, output destinations, stage restrictions, version
  pins and least-privilege workflow permissions express policy, not redundant
  defaults. Do not remove them merely to shorten a command.

Change overrides only after checking the pinned version and relevant regression.
Coinciding with an upstream default does not invalidate a tested safety boundary.

Lychee accepts HTTP 403/429; success does not prove content was served.
The offline docs gate checks local files, not external availability or anchors.

[Source selection](../src/agent_kit/infrastructure/catalog_adapter.py) prunes
bytecode, Git internals, Node dependencies and caches, not unexpected output.
Bytecode or links masquerading as caches in composed output still fail provenance.
The [APM adapter](../src/agent_kit/infrastructure/apm_adapter.py) owns its
900-second default and finite positive timeout requirement;
[smoke](../scripts/apm_smoke.py) bounds commands at 1800 seconds.
Both use the pinned environment's APM launcher, not an unrelated `PATH` entry.
The adapter discards subprocess output; smoke decodes failure bytes as UTF-8
with invalid bytes escaped. Nonzero exits/timeouts fail without skipping integrity.

## Scanner configuration discovery

A committed configuration is not proof that a hosted scanner reads it:

| Tool | Native CLI / pre-commit | CodeRabbit integration |
| --- | --- | --- |
| Ruff | Discovers the closest `ruff.toml`, `.ruff.toml`, or `pyproject.toml` | Same hierarchy; `config_file` is only needed to override it |
| ty | Discovers [ty.toml](../ty.toml); its include list covers source, scripts, tests, the guard and portable `packages` | No native integration; required CI still checks types |
| actionlint | This repository uses hook arguments, not a separate config; the tool also supports standard config-file discovery | Documents default configuration only; do not assume the hosted runner honors local exceptions |
| zizmor | Discovers `.github/zizmor.yml`, `.github/zizmor.yaml`, `zizmor.yml`, then `zizmor.yaml` at the repository root | Uses the same ordered list; repository policy replaces generated policy |
| Gitleaks / Betterleaks | Gitleaks uses `--config`, `GITLEAKS_CONFIG`, `GITLEAKS_CONFIG_TOML`, then the target's `.gitleaks.toml` | The `gitleaks` key runs Betterleaks with bundled defaults, not repository rules or Git history |
| OSV-Scanner | Discovers `osv-scanner.toml` beside each scanned file, not recursively; `--config` overrides discovery | Documents use of a repository `osv-scanner.toml` |
| detect-secrets | Baseline must be passed explicitly; our hook uses `--baseline .secrets.baseline` | Not a native integration; Betterleaks provides complementary advisory findings |

The repository and portable zizmor policies only set a 14-day Dependabot
cooldown; no disabled rules or allowlisted owners. actionlint's `-ignore` covers
only the pinned version's unsupported `$/` workflow-call diagnostic; remove it
when supported. Scanner-config edits rerun the actual workflows.

Do not add empty Gitleaks/OSV suppression files without a reviewed exception.
Hosted checks are advisory, may use different versions or skip an existing CI
run, and do not replace local secrets, audit, lint, type or workflow gates.
Ruff is not a secret scanner/advisory database; LanguageTool checks grammar.
Run `ty check` at the root; `ty check packages` reporting no Python files is not
evidence. The type hook also runs on `ty.toml`, `pyproject.toml` and `uv.lock`.
Consumers type-check rendered templates with their own framework dependencies.

Sources: [CodeRabbit tool behavior](https://docs.coderabbit.ai/tools/index),
[LanguageTool](https://docs.coderabbit.ai/tools/languagetool),
[Betterleaks](https://docs.coderabbit.ai/tools/gitleaks),
[hosted zizmor](https://docs.coderabbit.ai/tools/zizmor),
[hosted actionlint](https://docs.coderabbit.ai/tools/actionlint),
[zizmor discovery](https://docs.zizmor.sh/configuration/),
[actionlint configuration](https://github.com/rhysd/actionlint/blob/v1.7.12/docs/config.md),
[OSV configuration](https://google.github.io/osv-scanner/configuration/),
[Gitleaks configuration](https://github.com/gitleaks/gitleaks#configuration), and
[detect-secrets](https://github.com/Yelp/detect-secrets).

## Python exception contracts

`TRY003` and `TRY004` have no exemptions. Exception classes own diagnostics;
related domain failures may use a closed enum. Do not bypass these rules with
`noqa`, arbitrary-message wrappers or message variables at production raise sites.

Wrong input types raise `TypeError`; invalid values raise `ValueError`.
[InputTypeError](../src/agent_kit/core/errors.py) marks expected input failures:
catalog validation turns it into a finding and the CLI exits 1. Do not catch
unrelated `TypeError` bugs; preserve explicit failures and wrapped causes.

Portable scripts own local exceptions and run without toolkit imports.
Retain malformed-input, nonzero-exit and diagnostic regressions. Future templates
carry the conventions, not this toolkit's domain-specific hierarchy.

These choices follow the official
[TRY003 guidance](https://docs.astral.sh/ruff/rules/raise-vanilla-args/),
[TRY004 guidance](https://docs.astral.sh/ruff/rules/type-check-without-type-error/)
and Python's distinction between
[TypeError and ValueError](https://docs.python.org/3/library/exceptions.html#TypeError).

## JSON and VS Code

The [editor contract](editor.md#workspace-contract) owns recognized filenames.
Keep **.vscode/settings.json**, strict JSON and `check-json` without exclusions.
Renaming to **settings.jsonc** breaks discovery and removes current strict-hook
selection; it does not add JSONC validation. A future template needing comments
must keep the native filename, add tested JSONC validation in commits/CI and
exclude only those paths from strict checking.

## Repository-owned scripts and future Copier templates

Keep reviewed local-hook/Task scripts thin. Portable installed behavior belongs
in the package and must not assume a source checkout.

This repository is not yet a Copier template. When one is built:

1. Render only selected workflows/toolchains, not every toolkit guard.
2. Keep Task small, settings tool-owned and Bun/Node/Python pinned; no global or
   floating `latest` assumptions.
3. Keep recognized editor filenames; test discovery separately from validation.
4. Review trust before executable tasks/migrations. Never auto-enable them or
   initialize/publish consumer repositories.
5. Test fresh renders and supported updates in disposable projects: hooks,
   discovery, locks and CI. Review conflicts; preserve consumer facts/credentials.

## Primary references

- [Ruff's distinction between debug prints and CLI output](https://docs.astral.sh/ruff/rules/print/)
- [uv script metadata and isolated environments](https://docs.astral.sh/uv/guides/scripts/)
- [pre-commit configuration, stages and local hooks](https://pre-commit.com/)
- [Basic hook behavior](https://github.com/pre-commit/pre-commit-hooks/tree/v6.0.0)
- [CSpell hook manifest at v10.3.0](https://github.com/streetsidesoftware/cspell-cli/blob/v10.3.0/.pre-commit-hooks.yaml)
- [Bun run and the --bun flag](https://bun.sh/docs/cli/run)
- [Bun lockfile](https://bun.sh/docs/install/lockfile)
- [Pinned setup-bun action](https://github.com/oven-sh/setup-bun/tree/v2.2.0)
- [jscpd](https://github.com/kucherenko/jscpd/tree/v5.4.1)
- [lychee configuration at the pinned release](https://github.com/lycheeverse/lychee/blob/lychee-v0.24.2/lychee.example.toml)
- [yamllint configuration discovery](https://yamllint.readthedocs.io/en/stable/configuration.html)
- [VS Code workspace settings](https://code.visualstudio.com/docs/configure/settings)
- [VS Code JSON and JSONC](https://code.visualstudio.com/docs/languages/json)
- [pre-commit file classification](https://github.com/pre-commit/identify)
- [Task style guide](https://taskfile.dev/docs/styleguide)
- [Copier updates](https://copier.readthedocs.io/en/stable/updating/)
- [Copier trusted templates](https://copier.readthedocs.io/en/stable/configuring/#tasks)
