---
name: kit-codebase-audit
description: Use when auditing a whole repository and producing a ranked, evidenced findings report without fixing.
license: MIT
---

# Audit a codebase and rank the findings

An audit observes and ranks; it never fixes. Every finding carries a
`path:line` (or a command and its output), a severity, a confidence and the
skill that owns the remediation. Diff reviews belong to `kit-simplify-review`
and `kit-duplication-review`; this procedure covers the whole repository.

## Procedure

1. **Fix scope and baseline.** Record the commit, included and excluded paths
   (generated, vendored, fixtures, build output), the audit goal and a time box
   in the [audit plan](assets/audit-plan.md.template). Confirm the existing gates
   pass or record their current failures as the baseline.
2. **Inventory the repository.** Count files per language, list entry points
   (console scripts, `__main__` modules, app factories, workers, scheduled jobs),
   packages and their layers, test tiers, CI gates and existing tool
   configuration. Use `kit-graph-analysis` for the import graph and cycles.
3. **Choose deterministic tools.** Prefer tools the project already locks and
   configures. Judge any new tool with the
   [tool selection guide](references/tool-selection.md) (release recency,
   maintainers, downloads, license) and pin its version. Never add a dependency
   to the project during an audit; run new tools from a disposable, pinned
   environment approved by the operator.
4. **Run the tools first, read code second.** Capture machine-readable output in
   one audit directory, using the commands and
   [Ruff audit config](assets/ruff-audit.toml.template) and
   [pyproject audit snippets](assets/pyproject-audit.toml.template) listed in the
   guide: Ruff with complexity (`C90`, `PLR`) and selected families, a type
   checker (ty, mypy or pyright), import-linter contracts, vulture, deptry,
   duplication through `kit-duplication-review`, pip-audit or OSV-Scanner
   through `kit-supply-chain`, and cspell.
5. **Merge and rank tool output** with the
   [findings summarizer](assets/summarize_findings.py):

   ```text
   python assets/summarize_findings.py audit/ruff.json audit/osv.sarif audit/ty.json --root "$PWD" --output audit/tool-findings.md
   ```

   It accepts SARIF, Ruff JSON and GitLab Code Quality JSON, groups by tool and
   rule, ranks by level and count, and exits 1 when findings remain (2 on
   unreadable input). Run `--self-test` after editing it.
6. **Review manually where tools are blind.** Walk the lenses in
   [manual review](references/manual-review.md): dependency direction and
   ports versus adapters, naming (file versus class), magic numbers, docstrings,
   error handling, logging, configuration, tests by tier and documentation.
   Sample hot spots (churn times complexity) instead of reading everything.
7. **Grade every finding** with the
   [severity and confidence rubric](references/severity-rubric.md). Collapse
   repeated instances of one root cause into a systemic finding with a count.
8. **Route remediation.** Name the owner skill for each finding (for example
   `kit-refactor`, `kit-consistency`, `kit-hexagonal-architecture`,
   `kit-python-service`, `kit-supply-chain`, `kit-modernize`) and propose
   batches ordered by risk removed per unit of effort.
9. **Write the report** from the [audit report template](assets/audit-report.md.template):
   scope, baseline, inventory, ranked findings, systemic themes, what was not
   checked and why, and reproducible commands. Keep raw tool output beside it.
10. **Hand off without fixing.** Remediation starts as separate, owned changes;
    a gate added from the audit starts from a counted baseline and ratchets.

## Acceptance gates

- The plan records the commit, scope, exclusions and tool versions before any
  tool runs.
- Every finding has evidence (`path:line` or command output), severity,
  confidence and an owner skill; none rests on opinion alone.
- Tool results are reproducible from the recorded commands and configuration.
- Systemic issues are reported once with a count, not as hundreds of rows.
- Unchecked areas and tool blind spots are listed explicitly.
- No source, configuration, lockfile or baseline was modified by the audit.

Failure modes, recovery and primary sources are in the
[audit guide](references/guide.md).
