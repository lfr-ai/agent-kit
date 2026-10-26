# Lessons

## Windows reserved-path checks interpret drive prefixes

`ntpath.isreserved("a:metadata")` treats `a:` as a drive prefix rather than a
filename colon. When validating individual output components, reject colons
explicitly as well as reserved names. Evidence:
`test_single_letter_alternate_stream_is_rejected_before_any_write` covers all
52 ASCII letters and requires rejection before any filesystem writes.

## Keep the recorded coverage inventory explicit

New capabilities require an intentional update to `coverage.json`, the baseline
counts and digest in `scripts/check_coverage.py`, and the related regression
tests. Do not infer inventory changes from another checkout.

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

## Secret-shaped fixtures need explicit allowlist comments

detect-secrets flags placeholder passwords, example SHAs and revision IDs in
templates and tests. Mark each deliberate fixture inline with
`pragma: allowlist secret` instead of excluding test or template directories, so
real credentials added later are still caught. Evidence: the all-files hook run.

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
