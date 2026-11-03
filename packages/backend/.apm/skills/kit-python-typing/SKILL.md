---
name: kit-python-typing
description: Use when refining Python boundary records, callable signatures, or type predicates.
license: MIT
---

# Refine Python types without changing behavior

1. Trace the value from its decoded boundary to every consumer. Pin accepted,
   rejected, empty, and missing values before changing annotations.
2. Select concrete records and predicate semantics using the
   [typing guide](references/typing.md). Keep runtime validation explicit.
3. Use a `TypedDict` for existing dictionaries with stable keys; preserve the
   runtime dictionary and JSON shape. Do not introduce a record wrapper solely
   to make a type checker happy.
4. Choose `TypeIs` only for an if-and-only-if predicate; keep `TypeGuard` for
   partial validators. Test both branches, including empty values.
5. Preserve parameter kinds and result types when forwarding callables. Use
   `ParamSpec` rather than `Callable[..., object]` for transparent forwarding.
6. Fill the [review record](assets/typing-review.md.template), run the project's
   type checker and focused behavioral tests, and report unverified consumers.

Do not use `Any`, casts, or quoted annotations to bypass a boundary.

## Acceptance

- Runtime behavior and serialized keys are unchanged.
- Record fields have concrete types; optional keys and nullable values differ.
- Predicate annotations match both successful and unsuccessful checks.
- Public structured return docs explain keys/fields, ordering, and empty cases.
- No production abstraction is introduced without two current uses.
