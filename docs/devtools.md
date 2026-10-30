# Developer tooling

For contributors and automation authors: run recurring workflows through Task,
focused gates through the existing verifier, and one-off tools directly.
Do not add another Task target for every executable or repeat a tool's defaults.

## Entry points

| Need | Command |
| --- | --- |
| List the targets and their descriptions | `task` |
| Audit the lock, then install the Python environment and Git hooks | `task bootstrap` |
| Full read-only repository gate, including coverage | `task verify` |
| One gate, such as source, drift, roles or docs | `task verify -- source` |
| Locked dependency vulnerabilities (network) | `task verify -- dependencies` |
| Exact versions, frozen hooks and image digests | `task verify -- pins` |
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

The [Taskfile](../Taskfile.yml) follows the
[Task style guide](https://taskfile.dev/docs/styleguide): a schema comment for
editor validation, a `desc` on every target, a `default` target that lists them,
and `bootstrap` preconditions that name a missing uv or Bun instead of failing
mid-install. Editor tasks wrap these targets one to one; consumers start from
the portable Taskfile template in `kit-verify-change`.

Task defaults `AGENT_KIT_DIR` to the actual checkout for its subprocesses;
an existing process variable takes precedence in the pinned Task version.
On Windows, bootstrap additionally registers that path in the user environment;
the explicit registration task supports a moved clone. Restart the parent
editor/terminal before expecting other repositories to inherit it. Registration
does not install an agent hook or turn the path into a permission grant.

The tox matrix runs environments sequentially. Do not start it alongside another
test/coverage gate: interpreter isolation does not isolate shared report paths.

The verifier never synchronizes dependencies, including when selecting the
network audit. Provision the reviewed environment separately through bootstrap.
The full gate first runs `uv lock --check`, since suppressing environment
synchronization must not silently waive lock consistency. A stale lock fails
before code checks run; a missing tool remains an error rather than triggering
an installation. CI uses the same non-syncing command after explicit provisioning.

`task test` runs every tier. Select a fast subset with
`task test -- -m "not integration and not slow"`. Coverage remains enforced by
`task verify`; hooks are complementary, not a replacement for the test gate.
The conventions gate runs the shared AST checker over toolkit source and checks
Python docstrings and named numeric values in portable APM assets. Nontrivial
numeric literals must have names expressing intent and units; `0`, `1`, `-1`,
type annotations, and literal expectations in test modules are exempt.
The gate also uses `--templates --only magic-number` for production Python
templates; `test_*.py.template` and `conftest.py.template` retain fixture literals.
Docstrings use paired double-backtick
reStructuredText literals; Markdown prose retains CommonMark's single-backtick
inline syntax. The same gate runs on every pre-commit invocation.

## Hooks and runtimes

The [pre-commit configuration](../.pre-commit-config.yaml) installs pre-commit
and commit-msg hooks. `task bootstrap` audits the lock, syncs it, and installs
them; run it after operator-owned repository initialization.
Hook repositories are frozen to full commit SHAs and the link-check image is
pinned by digest. When `pyproject.toml` or `uv.lock` changes, the dependency audit
runs before any hook that syncs the environment, followed by the license check.
actionlint (with an exact Go toolchain) checks workflow correctness; zizmor checks
workflow, Dependabot, action, and pre-commit security. The actionlint hook carries
a narrow compatibility exception in its arguments, without a separate
configuration file. [.github/zizmor.yml](../.github/zizmor.yml)
sets a 14-day Dependabot default cooldown without disabling audits or restating
the default SHA-pinning policy. Changes to either
configuration rerun the scanners against the actual workflows. See
[dependency security](dependency-security.md).
The default stage is explicitly **pre-commit** because pre-commit's own default
is every supported stage. Commitizen alone selects **commit-msg**.
There are no manual-stage hooks: links and duplication run with ordinary checks.

On Windows, check `Get-Command uv -All` if hooks ignore `SKIP`: a version-manager
shim can change child environment variables. Invoke the native `uv.exe` or put
its directory first on that terminal's `PATH`. Do not rewrite user-global shims
as a repository repair.

Pre-commit manages the upstream Python and Node hook environments. Bun runs the
locked jscpd binary (`bun run --bun jscpd`) from [package.json](../package.json)
and [bun.lock](../bun.lock); `task bootstrap` installs it with
`bun install --frozen-lockfile`, and [bunfig.toml](../bunfig.toml) disables
dependency lifecycle scripts. Docker must be running for `lychee-docker`.
The recommended VS Code Container Tools extension helps manage containers but
does not install or start the Docker engine.
The Bun version used in CI is pinned to the locally exercised 1.3.11, not
claimed to be the newest available release. Changing execution to Bun does not
turn every upstream Node hook into a Bun hook or remove Node.js from the toolchain.

`--bun` deliberately runs the tool with Bun instead of its Node shebang. The hook
never downloads: a missing `node_modules` fails until bootstrap installs the lock.
The `version-pins` hook and `task verify -- pins` reject mutable hook revisions,
undigested images, package runners such as `npx`/`uvx`/`bunx`, unlocked installs,
and ranged tool requirements; see [version pinning](dependency-security.md#version-pinning).

Link checks now require network access and Docker during commits. Duplication
checks scan the repository once, not only changed files. Those are intentional
costs of removing manual stages; no timeout or failure is converted into success.
Run an individual hook with
`uv run --locked pre-commit run jscpd --all-files`.
The link hook's actual ID is `lychee-docker`, not `lychee`.

Generated skills, instruction mirrors, native agents and lockfiles are not
globally excluded from pre-commit. Read-only hooks can inspect them for secrets,
syntax, merge conflicts and filename safety. Only the four whitespace, newline,
line-ending and byte-order-marker fixers exclude these tool-owned outputs, using
one shared YAML anchor. Correct their canonical source and regenerate through
the owning tool instead of rewriting attested output independently.
The always-running drift and native-role checks still enforce provenance;
they complement rather than replace file safety checks. Lock-only changes also
reach the `uv lock --check` hook.

## Defaults and intentional overrides

- Large-file validation inherits upstream's 500 kB limit.
- Branch protection inherits upstream's `main` and `master` branch list.
- yamllint discovers its configuration; Import Linter discovers its own.
- CSpell inherits the upstream hook's filename handling and quiet-output flags.
  Hook `args` replace upstream arguments rather than append them. Removing the
  override restores `--gitignore --files` too; keeping just `--cache` would not.
  Cache is optional, not a correctness requirement.
- jscpd discovers [.jscpd.json](../.jscpd.json); lychee reads
  [lychee.toml](../lychee.toml). Nonstandard filenames would require explicit
  configuration arguments.
- The lychee v0.24.2 hook manifest still names its 0.23.0 Docker image. The entry
  explicitly selects 0.24.2 to match the pinned hook revision; this is a necessary
  compatibility override, not a duplicate default. Review that entry together
  with future hook-revision updates; remove it when upstream fixes its manifest.
- Ruff discovers [ruff.toml](../ruff.toml) and defaults to the current directory.
  This repository deliberately declares its Python 3.13 target and formatter
  settings. Complexity, branch, return and statement limits are 6, 8, 6 and 40;
  portable assets have no complexity exemptions. `TC` imports use postponed
  annotations rather than string-literal forward references. Command-line output
  uses stream writes instead of `print`, and every standalone asset script opens
  with PEP 723 metadata declaring Python 3.13 and `dependencies = []`.
  The assets use only the standard library. Run environment-inspection tools
  through the target environment's Python, not an isolated script environment.
  Neither `T201` nor `INP001` has a source exemption; Ruff and the metadata tests
  enforce these conventions.
- Commitizen inherits its Conventional Commits adapter and disabled automatic
  changelog rewriting. Coverage inherits standard report destinations and
  `skip_covered = false`; Markdown and YAML lint configurations omit unchanged
  rule defaults. Explicit strictness, coverage thresholds and project exclusions
  remain in their owning configurations.
- `--locked`, read-only format checks, LF normalization, test filename style,
  explicit secret baselines, output destinations, stage restrictions, version
  pins and least-privilege workflow permissions express policy, not redundant
  defaults. Do not remove them merely to shorten a command.

Other tool settings are not indiscriminately deleted: a setting can encode a
cross-platform contract or a tested safety boundary even when one release
happens to use the same value. Change an override only after reviewing the
owning tool's version, behavior and related regression.

The existing link policy accepts bot-blocked HTTP 403 and rate-limited HTTP 429
responses. A passing link scan therefore does not prove those destinations
actually served their content; inspect them separately when availability matters.

Capability composition excludes Python bytecode (`__pycache__`, `.pyc`, `.pyo`)
from authored bundles. Running or importing a checker must not change the
portable output. This is a source-selection rule, not a provenance exemption:
unexpected bytecode added to composed output is still rejected, as are links
masquerading as cache paths.
The source-path inventory also prunes Git internals, installed Node dependencies,
and test/type caches rather than traversing generated trees during every
composition. This does not exempt unexpected files in composed output.
APM subprocess output is handled without locale-dependent pipe decoding:
the private adapter discards it, while smoke failures render captured bytes
as UTF-8 with visible escapes for invalid bytes. Nonzero exits and timeouts
still fail. The adapter defaults to 900 seconds per APM command so cold
full-profile replays can finish on slower filesystems; explicitly supplied
timeouts must be finite and positive. The outer smoke-command bound is
1800 seconds. Both paths use the pinned environment's recorded APM launcher,
not an unrelated `PATH` entry. No audit, drift or integrity check is skipped.

## Scanner configuration discovery

Configuration is read by the tool that owns it, not by GitHub simply because it
is committed. The native hooks and hosted integrations do not all have the same
discovery rules:

| Tool | Native CLI / pre-commit | CodeRabbit integration |
| --- | --- | --- |
| Ruff | Discovers the closest `ruff.toml`, `.ruff.toml`, or `pyproject.toml` | Same hierarchy; `config_file` is only needed to override it |
| ty | Discovers [ty.toml](../ty.toml); its include list covers source, scripts, tests, the guard and portable `packages` | No native integration; required CI still checks types |
| actionlint | This repository uses hook arguments, not a separate config; the tool also supports standard config-file discovery | Documents default configuration only; do not assume the hosted runner honors local exceptions |
| zizmor | Discovers `.github/zizmor.yml`, `.github/zizmor.yaml`, `zizmor.yml`, then `zizmor.yaml` at the repository root | Uses the same ordered list; repository policy replaces generated policy |
| Gitleaks / Betterleaks | Gitleaks uses `--config`, `GITLEAKS_CONFIG`, `GITLEAKS_CONFIG_TOML`, then the target's `.gitleaks.toml` | The `gitleaks` key runs Betterleaks with bundled defaults, not repository rules or Git history |
| OSV-Scanner | Discovers `osv-scanner.toml` beside each scanned file, not recursively; `--config` overrides discovery | Documents use of a repository `osv-scanner.toml` |
| detect-secrets | Baseline must be passed explicitly; our hook uses `--baseline .secrets.baseline` | Not a native integration; Betterleaks provides complementary advisory findings |

The two zizmor policies (repository and portable template) only override the
Dependabot minimum default cooldown to 14 days. SHA pinning uses the pinned
tool's default; there are no disabled rules or allowlisted owners.
The actionlint hook's `-ignore` argument covers only the unsupported `$/`
workflow-call diagnostic in the pinned version. Remove it when the tool
supports that GitHub syntax.

No Gitleaks or OSV suppression file is needed without an actual, reviewed
exception. Do not create empty files or copy upstream defaults wholesale.
The deterministic gates remain detect-secrets, pip-audit/Bun audit, Ruff, ty,
actionlint and zizmor. Hosted advisory checks complement these, can use different
versions, and may be skipped when CodeRabbit detects an existing CI run.
Ruff is a linter, not a replacement for a dedicated secret scanner or dependency
advisory database. LanguageTool checks grammar rather than secrets or types.
Run `ty check` from the root: `ty check packages` alone still respects the
configured include list and must not be accepted if it reports no Python files.
The pre-commit type gate also reruns for edits to `ty.toml`, `pyproject.toml`,
and `uv.lock`, not just changed Python files.
Python templates are syntax- and convention-checked; the consumer type-checks
rendered templates with its own framework dependencies.

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

Ruff's selected `TRY` rules include `TRY003` and `TRY004`, without global or
per-file exemptions for either rule. Exception classes own their diagnostic
formatting; related domain failures may use a closed enum of invariant violations
instead of creating one class per message. Do not replace an exclusion with
`noqa`, arbitrary-message wrappers or local message variables at production raise
sites.

Wrong decoded input types raise `TypeError` subclasses; correctly typed but invalid
values raise `ValueError` subclasses. The toolkit's `InputTypeError` distinguishes
expected input failures from unrelated programming errors. Catalog validation
converts that specific input failure to a finding, and CLI boundaries report it
with exit status 1. They do not catch every `TypeError` and hide implementation
bugs. Existing value, filesystem and process failures remain explicit, and
wrapped failures retain their original cause.

Portable skill scripts own their local exception definitions and input handlers;
they must still run outside this checkout without importing the toolkit.
Retain malformed-input, nonzero-exit and actionable-diagnostic regressions when
changing an exception type. A future Copier template should carry these
conventions, not copy this toolkit's domain-specific exception hierarchy.

These choices follow the official
[TRY003 guidance](https://docs.astral.sh/ruff/rules/raise-vanilla-args/),
[TRY004 guidance](https://docs.astral.sh/ruff/rules/type-check-without-type-error/)
and Python's distinction between
[TypeError and ValueError](https://docs.python.org/3/library/exceptions.html#TypeError).

## JSON and VS Code

VS Code discovers workspace settings at **.vscode/settings.json**. It accepts
JSON with comments there despite the extension. Renaming that file to
**settings.jsonc** breaks discovery; it is not an improvement.

This repository uses strict JSON, a valid subset of JSONC, for all four workspace
files. Keep `check-json` enabled without exclusions. The stock hook selects the
`json` file type and uses Python's strict JSON parser. Merely changing a
file's extension to **.jsonc** does not give it comment-aware validation and,
with the current identify classifier, removes it from that hook's selection.

For a future template that deliberately needs comments, keep VS Code's mandated
filename, add a real JSONC validator, and exclude only those paths from strict
JSON checking. Wire the validator into commits and CI and retain malformed-input
regressions. Do not add that dependency to this strict-JSON repository preemptively.

## Repository-owned scripts and future Copier templates

Local hooks may call reviewed, tracked scripts. That is the normal pre-commit
`repo: local` model for repository-specific checks. Task also recommends external
scripts rather than complex inline shell. Keep these scripts thin and scoped;
portable installed behavior belongs in the package, not a script that assumes
it can find the source checkout.

This repository is not yet a Copier template. When one is built:

1. Render only workflows and toolchains the consumer actually selects; do not
   copy this capability toolkit's own guards into every application.
2. Keep a small recurring Task interface and tool-owned configuration. Select
   pinned Bun/Node/Python requirements explicitly; do not inherit a developer's
   user-global installation or use a floating `latest`.
3. Render VS Code's recognized filenames and strict JSON unless comments serve
   an actual need. Test discovery and validation separately.
4. Keep trusted template maintenance separate from consumer execution. Copier
   tasks and migrations can execute code and require reviewed trust; do not
   enable them automatically or initialize/publish consumer repositories.
5. Test fresh rendering and supported updates in disposable projects, including
   filenames, hook installation, tool discovery, lockfiles and the same CI gate.
   Review update conflicts; do not overwrite consumer-owned facts or credentials.

No Copier scaffolding or additional framework is needed for the present cleanup.

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
