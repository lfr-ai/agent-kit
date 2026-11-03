---
description: Apply to the toolkit Python implementation and tests.
applyTo: "src/**/*.py,tests/**/*.py"
---

- Core uses stdlib types only; source dependencies always point inward.
- Inject file/process boundaries; keep selection and checks independently testable.
- Narrow types instead of casting; tests may keep literal expected values.
- Keep functions within the Ruff complexity, branch, return, and statement limits by
  extracting named helpers; never suppress those limits.
- Use paired double-backtick literals for inline code in Python docstrings;
  keep Markdown prose in standard CommonMark single-backtick syntax.
- Use a one-line docstring when a callable has at most one parameter, a plain
  return, and no constraint, effect, or failure worth a section; public callables
  with two or more parameters need `Args:`.
- Catch specific failures and surface actionable diagnostics without credentials.
- Tests use temporary workspaces; never depend on personal configuration or real cloud data.
- A source-path calculation must not assume the package is installed in the consumer.
