---
description: Apply to the toolkit Python implementation and tests.
applyTo: "src/**/*.py,tests/**/*.py"
---

- Core uses stdlib types only; source dependencies always point inward.
- Inject file/process boundaries; keep selection and checks independently testable.
- Use concrete annotations, narrowing instead of casts, and immutable records.
- All dataclasses are keyword-only; immutable records are frozen and slotted.
- Do not introduce production Any or string-literal forward references.
- Name numeric literals other than 0 and +/-1 as `UPPER_CASE` constants that state
  intent and unit; tests may keep literal expected values.
- Keep functions within the Ruff complexity, branch, return, and statement limits by
  extracting named helpers; never suppress those limits.
- Use paired double-backtick literals for inline code in Python docstrings;
  keep Markdown prose in standard CommonMark single-backtick syntax.
- Catch specific failures and surface actionable diagnostics without credentials.
- Tests use temporary workspaces; never depend on personal configuration or real cloud data.
- A source-path calculation must not assume the package is installed in the consumer.
