# Lessons

## The Koda coverage baseline is a reviewed pin, not a live mirror

When Koda gains a skill, instruction, or script, `uv run --locked python -m scripts.check_coverage --source-root <koda>`
fails until `coverage.json` maps it, `_BASELINE_COUNTS`/`_BASELINE_KEYS_SHA256` in
`scripts/check_coverage.py` are regenerated from the new key sets, and the count asserts
in `tests/unit/repo_guards/test_capability_coverage.py` change. Run it after any Koda capability change.

## Overlapping scoped instructions cost context on every edit

Five instructions repeated the same bullets: three applied to `**/*.py`, two to every
file. They are now `kit-backend` + `kit-python-conventions` (Python) and `kit-safety`
(always-on). `tests/unit/repo_guards/test_context_budget.py` caps each profile at one always-on
instruction and two sharing a scope. Gotcha: a `:` inside a frontmatter
`description` breaks the YAML; `task verify -- source` reports it.

## Editing packaged text makes the built source archive stale

`uv run --locked python -m scripts.check_release` compares the archive with a fresh composition, so any change
under `packages/` (even one instruction line) fails it until the owned
`build/capabilities/*.zip` and its `build/release/` copy are removed and rebuilt
with `task capabilities:build`. Evidence: `source archive: invalid content or license`
after a docstring-guidance edit; passed after rebuilding.

## Docstring inline code uses single quotes

Owner decision: docstrings mark inline code with single quotes, never backticks.
Google and PEP 257 leave inline markup open and no renderer is configured, so this
is a portable default that consumers with Sphinx/Markdown rendering may override.
Evidence: `kit-python-service` skill and the `check_python.py` docstring rule.

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

## Secret-shaped fixtures need explicit allowlist comments

detect-secrets flags placeholder passwords, example SHAs and revision IDs in
templates and tests. Mark each deliberate fixture inline with
`pragma: allowlist secret` instead of excluding test or template directories, so
real credentials added later are still caught. Evidence: the all-files hook run.
