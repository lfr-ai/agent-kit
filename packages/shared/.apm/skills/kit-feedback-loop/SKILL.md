---
name: kit-feedback-loop
description: Use when a task's edits are done, to self-review against rules and criteria and decide to iterate or stop.
license: MIT
---

# Close each task with a bounded feedback loop

## Procedure

1. Set the loop budget before the first review: maximum iterations (default
   three), and the condition that ends the loop early. Record it in the
   [iteration log](assets/iteration-log.md.template).
2. Read the operating policy, matching instructions, relevant skill gates and
   acceptance criteria at review start. Refresh when scope or guidance changes
   or context is lost, not on every unchanged iteration. List required rules
   and their proving checks.
3. Run the project's deterministic checkers first, smallest scope first:
   formatter in check mode, linter, type checker, convention and architecture
   checks, focused tests. Resolve checker failures before subjective review;
   a passing checker does not refute an untested behavioral defect. The
   `kit-verify-change` skill owns the full gate and evidence rules; this loop
   only selects and re-runs what the change touched.
4. Review what checkers cannot see with the
   [review checklist](assets/review-checklist.md.template): naming, named
   constants, docstrings, typing, layer placement, error handling, tests for
   failure paths, and documentation drift. Cite `path:line` for each finding.
   Use the [review guide](references/review.md) to challenge and deduplicate
   findings, preserve independent assessment and verify revised patches.
5. Compare the result with each acceptance criterion and mark it met,
   partial or unmet, with the evidence that shows it.
6. Look for a simpler approach and for a standard tool that replaces custom
   code, following [behavior-preserving simplification](references/loop.md#simplify-without-losing-behavior).
   Check the current official documentation, not memory, for version claims.
7. Assess the change with the [rubric](assets/rubric.md.template) and decide
   with the [iterate or stop table](references/loop.md#iterate-or-stop):
   iterate only on findings that change correctness, contract or required
   conventions; stop when the budget is spent and report what remains.
8. When iterating, fix the highest-severity finding first, then return to
   step 3. Log each iteration: findings, change, checker results.
9. Record durable, evidenced lessons through the `kit-project-memory` skill;
   prefer turning a lesson into a check. Zero lessons is a valid outcome.
10. Report the final state: criteria status, checks run with results,
    remaining findings, lessons recorded, and why the loop stopped. Classify it
    as COMPLETE, ITERATE or BLOCKED using the rubric; budget exhaustion does not
    establish completion.

Failure modes and anti-patterns are in the [loop reference](references/loop.md).

## Acceptance gates

- The loop budget was set before the first review and not exceeded silently.
- Every rule listed in step 2 was checked by a tool or cited inspection.
- Deterministic checkers ran after the last edit, with exact commands and
  results recorded.
- Every acceptance criterion has a status and evidence; no unmet criterion is
  reported as done.
- Unavailable required checks are blockers, not out-of-scope exclusions; native
  behavior claims name the actual provider, host/harness and version exercised.
- A simpler alternative was considered and either adopted or rejected with a
  reason.
- Lessons, if any, have one home and evidence; nothing transient was stored.
