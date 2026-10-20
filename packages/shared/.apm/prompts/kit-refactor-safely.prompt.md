---
description: Restructure code in small behavior-preserving steps behind a green baseline and characterization tests, with a ledger of any difference.
argument-hint: Code to refactor and the goal, e.g. "split the order service"
agent: agent
---

# Refactor without changing behavior

Improve structure while callers observe exactly the same results, errors, and
side effects. Behavior changes, if requested, ship as a separate step.

## Input

- The user-supplied argument names the code and the structural goal. If it
  mixes a refactor with a feature, split them and confirm the order.

## Procedure

1. Load [kit-refactor](../skills/kit-refactor/SKILL.md) and follow its
   procedure and compatibility gates.
2. Name the contract to preserve: public names, signatures, defaults, error
   types, ordering, and side-effect timing. List every caller, including
   string references, serialization keys, entry points, and test patches.
3. Run the focused tests and record a green baseline. If coverage is thin,
   add [characterization tests](../skills/kit-refactor/references/characterization-tests.md)
   that pass against the unchanged code first.
4. When the goal is simplification, record complexity or duplication numbers
   before starting.
5. Apply one named transformation at a time from the refactoring catalog.
   Re-run focused tests after each. Undo a failing step instead of debugging
   forward.
6. For a change too large for one review, use parallel change or branch by
   abstraction so every intermediate state is releasable.
7. Move published names through an alias and deprecation, not a silent rename.
8. Delete the old implementation once no caller resolves it; do not leave dead
   copies.
9. Re-run the focused tests, the boundary checks from
   [kit-hexagonal-architecture](../skills/kit-hexagonal-architecture/SKILL.md)
   when modules moved, and the declared completion gate.

## Acceptance gates

- [ ] Green before the first step and after the last, with the same assertions.
- [ ] No test weakened, skipped, or deleted to pass.
- [ ] Every intentional difference is recorded with its authorization.
- [ ] Complexity or duplication claims come with before and after numbers.

## Output

The ordered list of transformations applied, files changed, the behavior
ledger (unchanged guarantees and any recorded differences), commands with
results, and any leftover alias with its removal step.
