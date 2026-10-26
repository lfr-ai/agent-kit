# Codebase audit guide

Commands, quality gates, failure modes and recovery for a whole-repository
audit. Tool choice is in [tool selection](tool-selection.md), the manual lenses
in [manual review](manual-review.md) and grading in
[the severity rubric](severity-rubric.md). Reviewed 2026-10-23.

## Command sequence

Run from the repository root with pinned tools. Write every output into one
`audit/` directory that is excluded from the scan itself. Use `--exit-zero` or
equivalent so one tool's findings do not stop the sequence; the summarizer
decides the exit status at the end.

| Step | Command (adapt paths) | Output |
| --- | --- | --- |
| Lint, complexity, security smells | `ruff check --config audit-ruff.toml --output-format json --exit-zero . > audit/ruff.json` | Ruff JSON |
| Types (ty) | `ty check --output-format gitlab --exit-zero > audit/ty.json` | GitLab Code Quality |
| Types (mypy or pyright) | `mypy --strict src` or `pyright --outputjson` | text or JSON, summarized by hand |
| Import contracts | `lint-imports` | contract pass/fail text |
| Dead code | `vulture` (reads `[tool.vulture]`) | `path:line: message (N% confidence)` |
| Dependency hygiene | `deptry . --json-output audit/deptry.json` | JSON with `DEP001`-`DEP005` codes |
| Complexity detail (optional) | `radon cc -s -n C src` and `radon mi -s src` | text |
| Duplication | follow `kit-duplication-review` (jscpd JSON report and its summarizer) | clone list |
| Vulnerabilities | `pip-audit --format json > audit/pip-audit.json` or `osv-scanner scan source --format sarif -r . > audit/osv.sarif` | JSON or SARIF |
| Spelling | `cspell --no-progress "**/*.{md,py}"` | text |
| Merge | `python assets/summarize_findings.py audit/ruff.json audit/ty.json audit/osv.sarif --root "$PWD" --output audit/tool-findings.md` | ranked Markdown |

Tools without SARIF, Ruff JSON or GitLab Code Quality output (import-linter,
vulture, deptry, radon, jscpd, cspell) are summarized as counts per rule with
two or three sample locations in the report; do not hand-convert them into
fake SARIF. Prefer Ruff JSON over Ruff SARIF: Ruff's SARIF marks every result
as `error`, while the summarizer grades Ruff JSON by code prefix. Use one Ruff
format, not both, or the summarizer counts each finding twice.

## Quality gates

| Gate | Pass condition |
| --- | --- |
| Scope | Commit, included paths, exclusions and goal recorded before the first run |
| Reproducibility | Every tool has a pinned version, a recorded command and kept raw output |
| Evidence | Every finding cites `path:line` or command output |
| Grading | Severity and confidence follow the rubric; high severity has high or medium confidence |
| Routing | Every finding names an owner skill and a remediation batch |
| Completeness | Unchecked areas and blind spots are listed, not silently skipped |
| Read-only | `git status` shows only the new `audit/` directory |

## Failure modes

- **Tool noise as findings.** Thousands of style violations bury three real
  defects. Collapse by rule into systemic findings and rank by severity, not
  count.
- **Configuration drift.** The audit runs a stricter Ruff selection than the
  project gate and reports the difference as defects. Label findings that come
  only from the audit configuration as "not enforced today".
- **False positives treated as fact.** Vulture and deptry miss dynamic use
  (plugins, entry points, reflection, `importlib`). Confirm each dead-code or
  unused-dependency claim with a text search and the import graph before
  grading it above low confidence.
- **Audit turned refactor.** Fixing while auditing hides the baseline and mixes
  review with change. Record the fix as a recommendation instead.
- **Scanning generated or vendored code.** Exclude it in the plan; otherwise
  rankings reflect code nobody maintains.
- **Unpinned tools.** A tool upgrade between runs changes the counts. Pin and
  record versions.
- **Vulnerability without reachability.** A vulnerable transitive package may
  not be reachable. Report it, state whether the vulnerable path is used, and
  route triage to `kit-supply-chain`.

## Negative cases

- A long function that is a flat table of mappings is not a complexity defect.
- An interface with one production adapter and one test fake is a port, not
  speculative abstraction.
- A numeric literal in a test expectation is not a magic number.
- A dependency flagged unused that is a runtime plugin or optional extra needs
  an ignore with a reason, not removal.

## Recovery

1. A tool crashes or times out: record the command, version and error under
   "not checked"; do not drop the area silently.
2. A finding is disputed: lower its confidence, attach the counter-evidence
   and keep it in the report until the owner decides.
3. The audit configuration is too noisy: narrow the rule selection in the plan,
   rerun, and state the change in the report.

## Primary sources

- [Ruff rules](https://docs.astral.sh/ruff/rules/) and
  [Ruff output formats](https://docs.astral.sh/ruff/settings/#output-format)
- [ty documentation](https://docs.astral.sh/ty/)
- [mypy documentation](https://mypy.readthedocs.io/en/stable/)
- [Pyright configuration](https://microsoft.github.io/pyright/#/configuration)
- [Import Linter](https://import-linter.readthedocs.io/en/stable/)
- [Vulture](https://github.com/jendrikseipp/vulture)
- [deptry usage](https://deptry.com/usage/) and
  [deptry rules](https://deptry.com/rules-violations/)
- [Radon](https://radon.readthedocs.io/en/latest/)
- [jscpd](https://github.com/kucherenko/jscpd)
- [pip-audit](https://github.com/pypa/pip-audit)
- [OSV-Scanner output formats](https://google.github.io/osv-scanner/output/)
- [CSpell](https://cspell.org/)
- [SARIF 2.1.0 specification](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html)
- [GitLab Code Quality report format](https://docs.gitlab.com/ci/testing/code_quality/#code-quality-report-format)
