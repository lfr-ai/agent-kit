# Tool selection for an audit

Prefer the tool the project already locks and configures; an audit that
introduces five new tools mostly measures configuration differences. Add a
tool only when a concern has no coverage, and judge it before trusting its
output. Reviewed 2026-10-23.

## Concern to tool

| Concern | Preferred | Alternatives | Notes |
| --- | --- | --- | --- |
| Lint, bug patterns, security smells | Ruff (`B`, `S`, `BLE`, `TRY`, `PL`) | Pylint, Bandit | Ruff reimplements most Bandit and Pylint checks; keep one source of truth |
| Complexity | Ruff `C90` (`C901`) and `PLR0911`/`PLR0912`/`PLR0913`/`PLR0915` | Radon `cc`/`mi`, Xenon gate | Radon adds maintainability index; see recency below |
| Types | the checker the project uses (ty, mypy or Pyright) | the other two | Do not switch checkers inside an audit; report the configured one |
| Layering and dependency direction | Import Linter contracts | the `kit-graph-analysis` import graph tool | Contracts make conclusions enforceable |
| Dead code | Vulture | Ruff `F401`/`F841`, coverage reports | Low confidence for dynamic code; confirm by search |
| Dependency hygiene | deptry (`DEP001` missing, `DEP002` unused, `DEP003` transitive, `DEP004` misplaced dev) | manual manifest review | Configure known plugins and extras first |
| Duplication | jscpd through `kit-duplication-review` | Pylint `duplicate-code` | Judge clones by reason to change, not size |
| Known vulnerabilities | pip-audit or OSV-Scanner through `kit-supply-chain` | platform advisories | OSV-Scanner reads many lockfile formats and emits SARIF |
| Spelling in code and docs | CSpell with a project dictionary | codespell | Add terms to the dictionary, not inline ignores |

## How to judge a tool

Collect the evidence, record it in the audit plan, and reject a tool that fails
a hard criterion even if it is popular.

| Criterion | Evidence | Hard limit |
| --- | --- | --- |
| Release recency | latest release date from the package index | a release within the last 18 months, or a stated maintenance-only policy |
| Maintainers | contributors active in the last year; organization ownership | more than one person able to publish, or an organization owner |
| Adoption | download statistics and dependents | none; low adoption raises the bar for every other criterion |
| License | SPDX identifier in package metadata and repository | compatible with the project's license allowlist |
| Security posture | security policy, signed or attested releases, OpenSSF Scorecard | a documented way to report vulnerabilities |
| Python support | classifiers and CI matrix | supports the project's minimum and newest Python |
| Output | JSON, SARIF or GitLab Code Quality | machine-readable output for repeatable merging |
| Configuration | `pyproject.toml` table or dedicated file | configuration can be committed and reviewed |

Where to look:

- Release history: `https://pypi.org/pypi/<package>/json` (`releases` upload
  times) or the package page.
- Downloads: [pypistats](https://pypistats.org/) for PyPI; npm download counts
  for JavaScript tools.
- Dependency and project health: [deps.dev](https://deps.dev/) and
  [OpenSSF Scorecard](https://scorecard.dev/).
- License identifiers: [SPDX license list](https://spdx.org/licenses/).

Network lookups are an operator action; record the date, the value and the
source URL so the judgment can be reviewed later.

## Recency snapshot

Latest releases observed on PyPI on 2026-10-23. Re-check before relying on them.

| Package | Latest release | Release date | Reading |
| --- | --- | --- | --- |
| import-linter | 2.15 | 2026-09 | active |
| pip-audit | 2.10.1 | 2026-06 | active, PyPA project |
| vulture | 2.16 | 2026-03 | active, single lead maintainer |
| deptry | 0.25.1 | 2026-03 | active, pre-1.0 |
| xenon | 0.9.3 | 2024-10 | slow |
| radon | 6.0.1 | 2023-03 | no release for over three years; prefer Ruff complexity rules |

Ruff and ty are pre-1.0 Astral projects with frequent releases; pin exact
versions because rule sets and diagnostics change between minor versions.

## Anti-patterns

- Choosing a tool by stars alone; stars do not measure maintenance.
- Running two tools for the same concern and reporting both counts.
- Installing an audit tool into the project's runtime dependencies.
- Copying a tool's default configuration without excluding generated code.

## Primary sources

- [PyPI JSON API](https://docs.pypi.org/api/json/)
- [pypistats](https://pypistats.org/)
- [deps.dev](https://deps.dev/)
- [OpenSSF Scorecard checks](https://github.com/ossf/scorecard/blob/main/docs/checks.md)
- [SPDX license list](https://spdx.org/licenses/)
- [Ruff rules](https://docs.astral.sh/ruff/rules/)
- [Radon](https://radon.readthedocs.io/en/latest/) and [Xenon](https://xenon.readthedocs.io/en/latest/)
- [deptry rules](https://deptry.com/rules-violations/)
