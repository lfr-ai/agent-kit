# Developer tooling

For contributors and automation authors: run recurring workflows through Task,
focused gates through the existing verifier, and one-off tools directly.
Do not add another Task target for every executable or repeat a tool's defaults.

## Entry points

| Need | Command |
| --- | --- |
| Install the locked Python environment | `task bootstrap` |
| Full read-only repository gate, including coverage | `task verify` |
| One gate, such as source, drift, roles or docs | `task verify -- source` |
| All tests, or a pytest selector | `task test`, `task test -- tests/integration` |
| Format, lint or types | `task format`, `task lint`, `task typecheck` |
| All pre-commit-stage hooks | `task precommit` |
| Conventional Commit authoring | `task commit` |
| Real APM delivery | `task apm:smoke` |
| Capability source archive | `task capabilities:build -- --profile fullstack` |

Run `uv run --locked python scripts/verify.py --help` to list gate names.
Use `uv run --locked python -m scripts.check_resources --json` for the resource
census, `uv run --locked python -m scripts.render_native --write` for an
approved native-role refresh, and the release guide for publication commands.
These are explicit operations, not additional aliases in Task or the editor.

`task test` runs every tier. Select a fast subset with
`task test -- -m "not integration and not slow"`. Coverage remains enforced by
`task verify`; hooks are complementary, not a replacement for the test gate.

## Golden-reference alignment

The neighboring reference project is a comparison point, not a dependency or a
file to copy blindly. This Python capability toolkit retains its own contracts:

| Reference pattern | Decision here |
| --- | --- |
| Local hooks and Bun execution | Reuse the pattern; jscpd is the only existing npx invocation |
| Standard commit stages | No manual stages; commit-message validation stays isolated |
| Strict JSON exceptions for commented editor settings | Unnecessary here: the workspace files contain strict JSON |
| Ruff hooks that fix files | Retain read-only hooks and the explicit `task format` authoring command |
| Unsafe YAML loading | Retain strict validation; these configs do not require custom YAML tags |
| Large-file and protected-branch overrides | Inherit upstream defaults rather than importing application-specific limits |
| Database, infrastructure and application guards | Do not activate tooling for applications this repository does not contain |
| One Task target per check | Keep ten recurring workflows; the verifier already selects individual gates |

The reference itself contains manual stages and repeated configuration
arguments. Those are not golden requirements to propagate into this repository
or a future template.

## Hooks and runtimes

The [pre-commit configuration](../.pre-commit-config.yaml) installs pre-commit
and commit-msg hooks. After operator-owned repository initialization, install
them with `uv run --locked pre-commit install --install-hooks`.
The default stage is explicitly **pre-commit** because pre-commit's own default
is every supported stage. Commitizen alone selects **commit-msg**.
There are no manual-stage hooks: links and duplication run with ordinary checks.

Pre-commit manages the upstream Python and Node hook environments. Bun is needed
for `bunx --bun jscpd@5.4.1`; Docker must be running for `lychee-docker`.
The Bun version used in CI is pinned to the locally exercised 1.3.11, not
claimed to be the newest available release. Changing execution to Bun does not
turn every upstream Node hook into a Bun hook or remove Node.js from the toolchain.

`bunx` is suitable for this pinned, standalone CLI. `--bun` deliberately overrides
its Node shebang; it is not an ordinary default to remove. An exact top-level
package version does not lock every transitive dependency. If stricter JS supply
chain reproducibility becomes a requirement, use one reviewed tooling manifest
and committed lockfile instead of inventing a package manager around each hook.

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
- Ruff discovers its configuration and defaults to the current directory.
  Its Python target comes from the package's `requires-python`; the standard
  88-column, double-quote and space-indent defaults need no restatement.
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

- [pre-commit configuration, stages and local hooks](https://pre-commit.com/)
- [Basic hook behavior](https://github.com/pre-commit/pre-commit-hooks/tree/v6.0.0)
- [CSpell hook manifest at v10.3.0](https://github.com/streetsidesoftware/cspell-cli/blob/v10.3.0/.pre-commit-hooks.yaml)
- [Bun package execution and shebang override](https://bun.sh/docs/cli/bunx)
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
