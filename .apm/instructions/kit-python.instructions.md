---
description: Apply to the toolkit Python implementation and tests.
applyTo: "src/**/*.py,tests/**/*.py"
---

- Core uses stdlib; dependencies point inward.
- Inject I/O; test selection and validation independently.
- Use concrete types and immutable records; no casts, production `Any` or quoted forward refs.
- Dataclasses are keyword-only; immutable records are frozen and slotted.
- Name numbers except 0 and +/-1 by intent/unit in `UPPER_CASE`; tests may use literal expectations.
- Meet Ruff complexity/branch/return/statement limits with helpers, not suppressions.
- Use double-backtick docstring literals; single backticks in Markdown.
- A one-line summary may suffice regardless of parameter count or visibility.
- Keep input/error/constraint contracts; do not restate signatures.
- Explain initializer arguments in double-backtick prose or `Args:`; validate supplied sections.
- Comment non-obvious intent, not the next statement.
- Catch specific failures; report actionable, credential-free diagnostics.
- Use temporary test workspaces, never personal configuration or real cloud data.
- Do not assume the consumer contains the toolkit.
