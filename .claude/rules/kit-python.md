---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
---

- Core uses stdlib types only; source dependencies always point inward.
- Inject file/process boundaries; keep selection and checks independently testable.
- Use concrete annotations, narrowing instead of casts, and immutable records.
- All dataclasses are keyword-only; immutable records are frozen and slotted.
- Do not introduce production Any or string-literal forward references.
- Catch specific failures and surface actionable diagnostics without credentials.
- Tests use temporary workspaces; never depend on personal configuration or real cloud data.
- A source-path calculation must not assume the package is installed in the consumer.
