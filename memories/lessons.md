# Lessons

## Windows reserved-path checks interpret drive prefixes

`ntpath.isreserved("a:metadata")` treats `a:` as a drive prefix rather than a
filename colon. When validating individual output components, reject colons
explicitly as well as reserved names. Evidence:
`test_single_letter_alternate_stream_is_rejected_before_any_write` covers all
52 ASCII letters and requires rejection before any filesystem writes.

## Keep the recorded coverage inventory explicit

New capabilities require an intentional update to `coverage.json`, the baseline
counts and digest in `scripts/checks/coverage/`, and the related regression
tests. Do not infer inventory changes from another checkout.

## Overlapping scoped instructions cost context on every edit

Five instructions repeated the same bullets: three applied to `**/*.py`, two to every
file. They are now `kit-backend` + `kit-python-conventions` (Python) and `kit-safety`
(always-on). `tests/unit/repo_guards/test_context_budget.py` caps each profile at one always-on
instruction and two sharing a scope. Gotcha: a `:` inside a frontmatter
`description` breaks the YAML; `task verify -- source` reports it.

## Editing packaged text makes the built source archive stale

`uv run --locked python -m scripts.checks.release` compares the archive with a fresh composition, so any change
under `packages/` (even one instruction line) fails it until the owned
`build/capabilities/*.zip` and its `build/release/` copy are removed and rebuilt
with `task capabilities:build`. Evidence: `source archive: invalid content or license`
after a docstring-guidance edit; passed after rebuilding.

## Python docstrings use double-backtick inline literals

Owner decision: use paired double-backtick reStructuredText literals for inline
code in Python docstrings; Markdown files retain CommonMark single-backtick code
spans. The shared checker and pre-commit gate enforce the docstring form.
Evidence: the Sphinx reStructuredText Primer and the `kit-python-service` checker.

## A local policy filename is not automatic enforcement

APM 0.33.0 native policy discovery can depend on remote organization configuration.
The supported workflow checks the local file explicitly; direct vendor invocation
is not a mandatory-policy boundary.
Evidence: [policy contract](../docs/policy.md) and its release-tag sources.

## Source layout and runtime discovery are different contracts

APM recursive compilation can discover unrelated optional sources in a monorepo.
Compose into an isolated selected source tree before invoking it.
Evidence: [compatibility](../docs/compatibility.md) and composition tests.

## Native delivery hashes differ from raw source hashes

APM 0.33.0 normalizes CRLF to LF for UTF-8, non-NUL per-file delivery hashes.
Source provenance keeps authored bytes exact; native ledger verification uses
the released normalization without removing lone carriage returns.
Evidence: provenance tests and the real install/compile/frozen smoke gate.

## Publication must not replace a competing empty directory

Ordinary POSIX rename can replace an empty destination created during staging.
The supported publisher uses Linux renameat2 with no-replace, or Windows rename;
unsupported platforms fail explicitly. Evidence: output race and containment tests.

## A successful legacy pack can contain no first-party capabilities

APM 0.33.0 `pack --format apm` returned zero for a root-only package but its ZIP
contained only a lockfile. Distribution uses an inspected, licensed source ZIP;
extract before installation. Evidence: source-archive tests and compatibility notes.

## uv writes an ignore marker beside distributions

`uv build` creates a one-byte `*` in the output directory's `.gitignore`.
The release inventory excludes only that exact regular marker, not arbitrary
hidden/stale products. Evidence: release inventory regression tests.

## Multiple upload paths do not imply a flat downloaded release

The pinned artifact uploader preserves directories beneath the common root.
Stage and verify one flat release inventory before upload; basename checksums
then match the downloaded artifact. Evidence: flat staging regression tests.

## Project reporting contacts are not portable skill resources

Root security/conduct documents can use valid private mail links without query
headers. Portable skills still reject mail links and retain their resource-link
boundary. Evidence: separate project-contact and portable-resource regressions.

## Source provenance is not independent release evidence

An archive can edit its own bytes and internal hashes together. Release checks
now compare it with a fresh composition from the canonical checkout, and coverage
checks pin the source-verified baseline identities rather than trusting counts.
Evidence: coordinated ZIP tampering and equal-count inventory regression tests.

## Research downloads do not belong in the repository root

Saved web pages from research (about 115 files, 35 MB) appeared beside project
documents, broke `agent-kit check` through their relative links, and stalled
detect-secrets. Validation now reads only declared root documents; keep downloads
in a session or temporary directory instead of extending `.gitignore` per filename.
Evidence: `test_unrelated_root_markdown_is_not_treated_as_project_context`.

## Secret-shaped fixtures belong in the reviewed baseline

detect-secrets flags placeholder passwords, example SHAs and revision IDs in
templates and tests. Do not exclude test or template directories, so real
credentials added later are still caught. Prefer recording audited false
positives in `.secrets.baseline` (`scan --baseline`, then `is_secret: false`):
entries match by hash, so they survive reformatting and need no per-line reason
for the suppressions gate. Inline pragmas need a reason and the formatter rules
below. Evidence: 37 audited findings across 23 files, 2026-11-12 hook run.

## detect-secrets filters normalized YAML lines

Its YAML scanner rewrites `rev: <sha>  # frozen: v1` as `rev: "<sha>"` and drops
the comment before line filters run. The baseline filter therefore matches only
an exact 40-hex `rev` value with optional quotes; the same value under another
key is still reported. Evidence: direct hook run and a non-`rev` probe.

## The pyenv uv shim treats less-than signs as redirection

`uv add 'package>=1,<2'` through `pyenv-win`'s `uv.bat` fails with "The system
cannot find the file specified" because `cmd` parses `<`. Use `~=` for the CLI
call, or edit `pyproject.toml` and run `uv lock`. Evidence: the pip-audit addition.

## Hashed build constraints need a newer minimum uv

Current uv documents `build-constraint-dependencies` entries as tables with
`requirement` and `hashes`, but uv 0.10 rejects that form ("invalid type: map,
expected a string"). Keep exact string pins until `required-version` is raised.
Evidence: `uv lock` failed with the table form and passed with string pins.

## A pinned role model that the host lacks disables the role

Copilot role files rendered with `model: ["GPT-5 mini", "Claude Haiku 4.5"]`
failed to start in a Copilot SDK host with "Model 'GPT-5 mini' is not
available"; the host did not fall back to the next list entry. Role assets now
omit `models`, so roles inherit the caller's model. Hosts cache role definitions
for the session, so the fix applies to new sessions. Evidence: the failed
`kit-plan-architect` delegation and the re-rendered native ownership check.

## The file-creation tool writes CRLF into Markdown and YAML

Files made with the `create` tool had CRLF endings, which fail the mixed
line-ending hook and prompt frontmatter parsing (`split("---\n")`). Ruff
normalizes Python but not Markdown, templates or YAML. After creating such a
file, rewrite it with LF. Evidence: `test_prompts_resources` failed on a new
prompt until its endings were normalized.

## `uv run` costs tens of seconds on a synced folder; measure the venv

On this OneDrive checkout `uv run --locked python -c pass` took 37s while the
venv interpreter started in 1s, and file opens took about 8 ms each. Time the
code with `.venv\Scripts\python.exe` before blaming it, and move the checkout out
of the synced folder. Evidence: provenance took 5s directly and 56-77s through
`uv run`.

## User-scope APM install delivers instructions and prompts but not agent roles

`apm install -g lfr-ai/agent-kit/packages/shared --target claude,copilot`
(APM 0.33.0) wrote skills to `~/.agents/skills` and `~/.claude/skills`,
instructions to `~/.claude/rules` and `~/.copilot/instructions`, and prompts to
`~/.claude/commands` and `~/.copilot/prompts`. Native agent roles were not
delivered; Claude drops the `agent:` prompt field with a warning. Evidence: a
throwaway `USERPROFILE` install.

## Reproduce the Ubuntu CI leg in a container before pushing

A test that faked `sys.platform = "win32"` passed on Windows and failed on
Ubuntu CI, because `shutil.which` then called Windows-only `_winapi`. Run the
whole gate in `ghcr.io/astral-sh/uv:<pinned>-python3.13-trixie-slim` from a
tarball of `git ls-files -co --exclude-standard`, copied with `docker cp`:
PowerShell re-encodes bytes piped to a native command, and a OneDrive bind
mount is too slow to copy. The Linux gate ran in about 4 minutes. Evidence:
CI run 40330605897 and the container verify that reproduced and then cleared it.

## Workers may not reach for package runners

Delegated workers ran `npx`, `uv run --with` and ad hoc containers to lint
files, which bypasses the pinned toolchain. Lint changed files through the
pinned hooks instead: `uv run --locked pre-commit run <hook> --files ...`.
Worker briefs must name this rule explicitly. Evidence: three workers in the
delivery-platform round, corrected in the worker brief.

## Refresh native roles with the render script after editing agents.json

There is no Task target for role projections. After changing
`kit-agent-runtime/assets/agents.json`, diff `scripts.render_native.expected`
against the checked-in files, then run
`uv run --locked python -m scripts.render_native --write`; the write refuses to
overwrite a hand-edited projection. Evidence: the `optional_workers` change
drifted only the two `kit-orchestrator` files, and `task verify -- roles` then passed.

## Exact applyTo comparison misses overlapping globs

`test_context_budget.py` counted identical scope strings, so `**/*.py` and
`**/test_*.py` from different bundles stacked unnoticed. Match representative
paths with `PurePosixPath.full_match` and bound the instruction count and
characters per path. Evidence: a Python test file loads 7 instructions,
about 10.8k characters, with every bundle installed.

## Research scratch cleanup must name owned artifacts

A research worker's repository-root `*.md`/`*.txt` cleanup deleted twelve clean
tracked context documents. Work paused; only the known baseline files were
restored and checked byte-identical before resuming. Use an explicit disposable
scratch directory and exact owned cleanup paths; a read-only assignment is not
filesystem isolation. Evidence: the 2026-10-28
[review execution record](../docs/agentic-development-review.md#12-verification-and-execution-notes).
It recurred on 2026-11-11: a research worker saved downloads to the repository
root and seventeen root `*.md`/`*.json` files were deleted. Every worker prompt,
including read-only research, must name an absolute scratch directory outside
the checkout.

## Hash-locked generated outputs must be excluded from text fixers

`profiles/native/**` is rendered without a final newline and hash-locked in
`profile-lock.json`. Until it was in the pre-commit `owned_outputs` anchor,
`end-of-file-fixer` appended a newline under `--all-files` and
`task verify -- profiles` failed. Add every new generated tree to
`owned_outputs`. Restore drifted files with the renderer, not by hand.
Evidence: the `profiles/native` case in `test_devtool_workflow.py`.

## detect-secrets pragmas must survive formatters

When a pragma is unavoidable, it needs a reason (`scripts/checks/suppressions.py`).
Inline `pragma: allowlist secret` works in Python, YAML, Bicep and HCL.
`pragma: allowlist nextline secret` on its own line works for Python and Bicep
but not YAML. Use the nextline form where ruff would wrap the line or the
Bicep formatter would move a trailing comment. Evidence: a 2026-11-12 control
probe with the pinned detect-secrets 1.5.0 hook.

## APM 0.35.0 staged activation can fail transiently on Windows

`task apm:smoke` failed three times with `WinError 5 Access is denied`: twice
in APM's staged-activation rename and once in the native fixture relocation.
This is upstream microsoft/apm#3386, fixed in APM 0.35.1. Retry the smoke, and
upgrade only through the reviewed dependency workflow once the cooldown allows.
Evidence: [compatibility notes](../docs/compatibility.md#smoke-process-boundaries).

## A failing Terraform variable validation hides dependent checks

If a validation on variable A reads variable B, and B fails its own validation,
Terraform treats A as unknown and skips every check that reads A. A test that
expects a production guard to fail then reports `Missing expected failure`.
Put a cross-variable check on a variable that no other guard reads, or have it
read only variables that have no validation, so a failing input can never make
a guarded value unknown. Evidence: the container-apps
`reject_production_defaults`, `reject_internal_without_subnet` and
`reject_internal_with_private_endpoint` runs in
`packages/delivery/infra/container-apps/terraform/tests/foundation.tftest.hcl`.

## Splitting a vendored Bicep module must extend the vendor closure

The starter's `vendor_bicep.py` copies an explicit file set, so a module split
into local files compiles in the toolkit but breaks every generated Bicep
project. The `_fixture_vendor` helper in `tests/integration/starter/test_iac.py`
now requires each vendored module to match its source `bicep/` directory for
every test render that vendors (the `acr` service matrix; no test vendors a
`ghcr` render).

## Compose environment overrides env_file, so pin in-network ports

A generated project's `.env` serves both the host-run app and Compose. Compose
`environment:` wins over `env_file`, so the app service pins
`APP_POSTGRES_PORT: "5432"` while the published host port follows
`${APP_POSTGRES_PORT:-5432}`. Manual E2E found the hard-coded host port 5432
colliding with a native PostgreSQL service. Evidence:
`test_compose_postgres_host_port_follows_settings` in
`tests/integration/starter/test_services.py`.

## One writer per working tree

Two agent sessions edited this checkout at the same time twice: once files
disappeared mid-task, and once a half-applied rename left tests importing a
module that did not exist yet. Before a commit or a full `task verify`, check
for a concurrent writer: `git status --porcelain` stable for several minutes and
no newer file times. Give each parallel session its own `git worktree add`
checkout and branch instead of sharing one tree.