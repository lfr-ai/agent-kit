---
name: kit-change-plan
description: Use when a change spans modules, modifies a shared contract, or needs phased rollout.
license: MIT
---

# Plan proportionately

## Procedure

1. State the requested observable outcome, its boundaries and non-goals. Decide
   the plan size: a trivial local edit needs a few lines, not a document.
2. Trace affected callers, existing helpers, contracts and ownership before
   proposing anything new.
3. Write [acceptance criteria](references/acceptance-criteria.md) that are
   observable, binary and cover failure paths; map each to a proving test.
4. Break the work into [vertical slices](references/vertical-slices.md): a
   tracer bullet first, then slices ordered by risk and value, each with its
   failing regression and completion command. Use the
   [slice template](assets/slice.md.template) for any slice that is not trivial.
5. Record data, security, compatibility, operational and knowledge risks in a
   [risk register](references/risk-register.md); turn high-impact risks into
   early slices, tests, spikes or approvals.
6. Write the [rollback plan](references/rollback-plan.md) for each slice: undo
   action, point of no return, trigger and verification. Rehearse it when data
   or deployment order changes.
7. Fill the [change plan](assets/plan.md.template) with criteria, slices,
   risks, rollback, stop conditions and the verification commands, before
   editing.
8. Record actual prerequisites, not list order; independent slices may run in
   parallel only with disjoint paths and one owner per shared contract.
9. Reassess after each slice and whenever evidence contradicts the plan; update
   the remaining slices instead of forcing code into an obsolete design.
10. Stop before destructive or irreversible work when ownership, approval or
    rollback is unknown.

Use tools and external documentation only where they resolve a concrete
uncertainty. The [planning gates](references/guide.md) summarize the rules.

## Acceptance gates

- Every acceptance criterion is observable, binary and mapped to a test; failure
  paths are covered.
- Every slice is end to end, names its criteria, paths, prerequisites, failing
  regression and completion command.
- Each high-impact risk has a response and a matching rollback entry; accepted
  risks name who accepted them.
- Irreversible steps are last, separate and explicitly approved.
- Verification commands are executable in the declared environment, and the
  plan records baseline and final results.
