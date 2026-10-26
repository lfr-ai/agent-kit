# Quality gate catalog

A gate is the set of checks a change must pass before it is called done. This
catalog lists the gate families a repository can adopt, what each proves,
typical Python-first tools, and where each runs. Choose per repository with the
[gate plan template](../assets/gate-plan.md.template); order and check-only
rules are in [gate ordering](gate-ordering.md) and parity rules in
[pre-commit and CI parity](precommit-ci-parity.md). Review date: 2026-10-23.

## Catalog (fast to slow)

| # | Gate | Proves | Typical tools | Scope | Pre-commit stage | CI |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Lockfile current | the lock matches the manifest | `uv lock --check`, `bun install --frozen-lockfile` | project | pre-commit | every push |
| 2 | Format | one canonical layout | `ruff format --check`, Prettier `--check` | changed files | pre-commit | every push |
| 3 | Lint | known bug patterns, style, security smells | Ruff (including `S`), ESLint, ShellCheck, actionlint | changed files | pre-commit | every push |
| 4 | Types | contracts across modules | ty, mypy, Pyright, `tsc --noEmit` | project | pre-commit (if fast) or pre-push | every push |
| 5 | Architecture and import contracts | dependency direction, forbidden imports | import-linter, custom AST checkers | project | pre-commit | every push |
| 6 | Docs, spelling, Markdown, links (local) | prose and configuration are correct | CSpell, markdownlint-cli2, local link checker, YAML/TOML/JSON schema checks | changed files | pre-commit | every push |
| 7 | Secrets (working tree) | no credentials committed | detect-secrets with an audited baseline, gitleaks | changed files | pre-commit | every push |
| 8 | Unit and property tests | behavior of rules and invariants | pytest with Hypothesis | test tiers | pre-push or manual | every push |
| 9 | Coverage | the tests exercised changed branches | coverage.py with `branch = true` and `fail_under` | full suite | manual | every push |
| 10 | Integration and contract tests | real boundaries work | pytest with disposable services | integration tier | manual | every push or pre-merge |
| 11 | Dependency audit | no known-vulnerable locked packages | `pip-audit` or `uv` audit tooling, OSV scanners | lockfiles | manual | every push and scheduled |
| 12 | Licenses | dependency licenses are allowed | license allow-list checker over the lockfile | lockfiles | manual | every push |
| 13 | External links, full-history secrets, mutation tests | slow or network-bound evidence | lychee, history secret scan, mutmut | repository | manual | scheduled or pre-merge |
| 14 | Build and package | the artifact builds and installs | `uv build`, install from the wheel in a clean environment | project | manual | pre-merge and release |

Not every repository needs every row. A documentation-only repository may stop
at row 7; a library adds rows 8 to 14. Record skipped rows and why.

## Selecting gates

- **One primary scanner per risk and target**: reuse existing tools before adding
  another engine. `kit-supply-chain` owns the selection table; image scanning and
  release SBOMs are not automatic additions to lockfile or secret checks.
- **Fast rows first**: rows 1 to 7 must stay under about ten seconds on a
  typical change so nobody bypasses the hooks.
- **Project-wide tools** (types, import contracts, tests) take no file names
  (`pass_filenames: false`) and run on the whole project.
- **Network rows** (dependency audit, external links) run in CI and on a
  schedule, never as a hidden part of a local check-only gate.
- **Thresholds live in configuration** (`fail_under`, complexity limits,
  allowed licenses), never in command lines that CI and hooks could disagree on.
- **One definition**: the gate script or task runner defines the rows;
  pre-commit and CI call it. CI runs every row with keep-going and uploads a
  report.

## Pre-commit stages

| Stage | Runs on | Put here |
| --- | --- | --- |
| `pre-commit` | staged files at commit | rows 1 to 7 |
| `pre-push` | commits about to be pushed | types and unit tests when they are too slow for every commit |
| `commit-msg` | the message | Conventional Commits check, when enforced in CI too |
| `manual` | `pre-commit run --hook-stage manual --all-files` | the full gate and slow rows |

## Failure modes

- A gate that only exists in CI, so developers learn about failures late.
- A hook that formats files during a "check", hiding unreviewed rewrites.
- Coverage measured on lines only, with a threshold lowered to pass.
- License and audit checks that read the manifest instead of the lockfile.
- Skipped rows reported as passed.

## Verification

1. List each adopted row in the gate plan with its exact command.
2. Break one row on purpose (a formatting error, a failing test) and confirm
   the hook, the local gate and CI all fail at that row.
3. Confirm the CI report lists every row with pass, fail, skipped (with
   reason) or unavailable.

## Primary sources

- [pre-commit: stages and hook types](https://pre-commit.com/#confining-hooks-to-run-at-certain-stages)
- Ruff, [linter](https://docs.astral.sh/ruff/linter/) and [formatter](https://docs.astral.sh/ruff/formatter/)
- [import-linter](https://import-linter.readthedocs.io/)
- coverage.py, [branch coverage](https://coverage.readthedocs.io/en/latest/branch.html)
- [pip-audit](https://github.com/pypa/pip-audit) and [OSV](https://osv.dev/)
- [detect-secrets](https://github.com/Yelp/detect-secrets)
- [lychee](https://lychee.cli.rs/)
- OpenSSF, [Scorecard checks](https://github.com/ossf/scorecard/blob/main/docs/checks.md)
