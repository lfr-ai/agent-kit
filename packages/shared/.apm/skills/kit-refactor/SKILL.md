---
name: kit-refactor
description: Use when restructuring code while preserving its observable contract and keeping the change narrowly scoped.
license: MIT
---

# Refactor against a preserved contract

## Procedure

1. Name the behavior and callers that must remain unchanged, and list any
   requested behavior change separately; it ships in its own step.
2. Read the affected implementation, public interface and tests. Search for
   indirect callers: reflection, string references, serialization keys,
   configuration, entry points and test patch targets.
3. Establish a green baseline with the smallest existing checks. Where coverage
   is weak, add [characterization tests](references/characterization-tests.md)
   at the boundary callers observe, controlling time, randomness and I/O.
4. Record complexity for the touched code as described in
   [measuring complexity](references/complexity.md) when the goal is
   simplification.
5. Choose transformations from the [refactoring catalog](references/catalog.md)
   and apply one at a time, re-running focused tests after each step. Undo a
   failing step instead of debugging forward.
6. Before merging similar code, decide whether it is the same knowledge or
   incidental duplication using [DRY versus incidental duplication](references/duplication.md).
7. For changes too large for one reviewable step, use strangler fig, branch by
   abstraction or parallel change from [large refactorings](references/large-scale.md),
   keeping the system releasable after every merge.
8. Keep public names, defaults, error types, ordering and side-effect timing
   stable. Published names move through an alias and deprecation, not a rename.
9. Move logic with its tests, adapt imports and registrations, and delete the
   old implementation once no caller resolves it.
10. Re-run the owning gate after the final step, and install or import from
    outside the source tree when modules or package data moved.
11. Fill the [behavior ledger](assets/behavior.md.template) and report every
    intentional difference and compatibility risk.

The [compatibility gates](references/guide.md) apply to every step.

## Acceptance gates

- Tests were green before the first step and after the last, with the same
  assertions; none were weakened or deleted to pass.
- Ordinary, boundary and invalid inputs produce the same results, exceptions
  and side effects as before, except where the ledger records an authorized
  difference.
- No duplicate implementation, temporary comparison test or migration alias is
  left without an owner and removal step.
- Complexity or duplication claims are backed by before/after numbers.
- Unrelated cleanup is absent from the diff.
