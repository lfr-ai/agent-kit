# Python service guide

## Purpose

A review checklist for a typed Python service or boundary adapter with clear
tests and failure modes. Topic detail lives in the sibling references linked
from [SKILL.md](../SKILL.md).

## Acceptance gates

- Unit and regression tests for public behavior and negative cases exist and run
  locally without network access or personal configuration.
- Error contracts are documented and stable across releases.
- The start-up path does not depend on developer-only files or secret defaults;
  missing configuration fails fast with the offending key named.
- Layer imports follow the [dependency rule](package-layout.md#dependency-rule).

## Review checklist

| Area | Question | Reference |
| --- | --- | --- |
| Signatures | Are options keyword-only and free of positional booleans? | [signature design](signature-design.md) |
| Records | Frozen, keyword-only, slotted; validated in '__post_init__'? | [dataclasses and enums](dataclasses-enums.md) |
| Branching | Is a repeated type switch replaced by a port or exhaustive 'match'? | [polymorphism](polymorphism.md) |
| Special methods | Do equality and hashing match value or identity semantics? | [dunder methods](dunder-methods.md) |
| Errors | Are vendor errors translated in adapters and chained? | [error handling](error-handling.md) |
| Logging | One structured event per handled failure, no secrets? | [logging](logging.md) |
| Docs | Do docstrings state constraints, side effects, and raised errors? | [docstrings](docstrings.md) |
| Layout | Is every adapter constructed only in the composition root? | [package layout](package-layout.md) |
| Ordering | Are helpers placed below their sole caller? | [method ordering](method-ordering.md) |

## Failure modes

- Unhandled exceptions that leak stack traces or vendor messages to clients.
- Silent swallowing of validation errors leading to inconsistent behavior.
- Tight coupling to framework request objects in core logic.
- Module-level singletons that make import order the wiring order.
- Retries around non-idempotent operations that duplicate side effects.
- Logs that contain tokens, connection strings, or personal data.

## Verification prerequisites

- Static checks: [check_python.py](../assets/check_python.py),
  [check_method_ordering.py](../assets/check_method_ordering.py), and
  [check_backend_wiring.py](../assets/check_backend_wiring.py) on touched paths,
  plus the project's formatter, linter, and type checker.
- A small runtime smoke test of the service entry point built through the
  composition root with fakes.
- Explicit negative-case tests for invalid input and dependency failures.

## Recovery

- Return typed, documented errors and avoid partial side effects; validate
  before mutating and rely on the storage transaction for multi-write changes.
- Keep compatibility adapters for public surface changes only while a real
  consumer depends on the old shape, with a test and a removal condition.

## Scope and limits

This guide focuses on service structure, typing, and testability. Static checks
are structural; they do not prove runtime performance, concurrency safety, or
operational readiness.

## Sources

- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [PEP 8 - Style guide for Python code](https://peps.python.org/pep-0008/)
- [typing - Support for type hints](https://docs.python.org/3/library/typing.html)
- [ast - Abstract syntax trees](https://docs.python.org/3/library/ast.html)
