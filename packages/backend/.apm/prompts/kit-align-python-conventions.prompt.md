---
description: Align Python code with typed-service conventions for signatures, records, errors, logging, docstrings, and import direction, running the bundled checkers.
argument-hint: Python package, module, or path to align
agent: agent
---

# Align Python code with project conventions

Bring one Python area in line with the typed-service conventions without
changing its observable behavior.

## Input

- The user-supplied argument names the package, module, or path. When it is
  empty, use the Python files changed in the working tree.

## Procedure

1. Load [kit-python-service](../skills/kit-python-service/SKILL.md). Read the
   project's own lint, type, and convention configuration first; project rules
   win where they are stricter or different.
2. Run the focused tests for the area and record a green baseline. If the
   baseline is red, stop and report it.
3. Run the skill's checkers over the target path and the project's linter and
   type checker. Collect findings into one list grouped by rule.
4. Fix signatures: full annotations, keyword-only options, no positional
   booleans, explicit units, one return shape. No production `Any`, casts, or
   quoted forward references.
5. Fix records and value sets: immutable dataclasses with `frozen=True`,
   `kw_only=True`, `slots=True`; string enums with explicit persisted values.
6. Fix errors: specific documented exception types chained with `from`,
   transport mapping only at the presentation edge, nothing swallowed.
7. Fix logging: one stdlib logger per module, structured context, no secrets or
   personal data in messages or `repr`, no duplicate logging at several layers.
8. Fix import direction: inner layers import no framework, ORM, or SDK; only the
   composition root constructs adapters.
9. Add or correct docstrings for public members, including `Args:`,
   `Returns:`, and `Raises:`.
10. Review filenames, module/subfolder cohesion and central ownership. Choose
    functions, partials and decorators with the
    [callable decision guide](../skills/kit-python-service/references/callables-and-decorators.md);
    test binding, metadata, errors and async behavior where they apply.
11. Make each fix a small step and re-run the focused tests between groups.
    Leave behavior changes for a separate, approved change.
12. Run the checkers, linter, type checker, and the declared completion gate.

## Acceptance gates

- [ ] Checker, lint, and type findings for the target path are zero or each
      remaining one is listed with a reason.
- [ ] Tests are green with unchanged assertions.
- [ ] No behavior, public name, or error type changed without being reported.

## Output

Findings fixed per rule (count and example `path:line`), any findings left with
reasons, files changed, and the commands run with results.
