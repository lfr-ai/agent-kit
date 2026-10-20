---
description: Review a diff or module for over-engineering and apply only behavior-preserving simplifications, with tests protecting each cut and a debt ledger.
argument-hint: Diff, module, or feature path to simplify
agent: agent
---

# Simplify without losing behavior

Remove complexity that does not pay for itself: speculative abstractions,
reinvented standard library features, unused flexibility, and duplicate
knowledge. Required behavior, error handling, and observability stay.

## Input

- The user-supplied argument names a diff, module, or feature path. When it is
  empty, review the working-tree diff. Never widen to the whole repository.

## Procedure

1. Load [kit-simplify-review](../skills/kit-simplify-review/SKILL.md) and follow
   its review lenses. For repeated code, also use
   [kit-duplication-review](../skills/kit-duplication-review/SKILL.md).
2. Write down the scope and the behavior that must not change.
3. Inventory the abstractions in scope: classes, interfaces, factories,
   wrappers, configuration options, and dependencies, with their callers.
4. Apply the lenses: is it used, is it needed now, does the standard library
   or platform already do it, does it hide a single call, does it duplicate
   the same knowledge elsewhere?
5. Classify each finding as delete, inline, replace, narrow, or keep, with one
   line stating what replaces it.
6. Present the findings and apply only those that are clearly safe or that the
   user approved. Keep public interfaces stable unless the user approved a
   breaking change.
7. Before each cut, make sure a test covers the behavior that must survive;
   add a characterization test if none does.
8. Apply one finding at a time and run the focused tests after each.
9. Where you deliberately accept a simpler but limited solution, record it as
   a dated, owned debt marker so it can be revisited.
10. Run the package suite, linters, and type checks. Report line, dependency,
    or complexity deltas measured, not estimated.

## Acceptance gates

- [ ] Every applied cut has a passing test that protects the kept behavior.
- [ ] No error handling, validation, or logging needed in operation was removed.
- [ ] Each finding names its replacement or the reason to keep it.
- [ ] Deltas are measured.

## Output

One line per finding (location, classification, replacement, applied or
proposed), the measured deltas, debt markers added, and commands run with
results.
