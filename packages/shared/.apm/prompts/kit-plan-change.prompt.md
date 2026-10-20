---
description: Plan a change as observable acceptance criteria, risk-ordered vertical slices, and a rollback path before any file is edited.
argument-hint: The change to plan, e.g. an issue link, a goal, or the affected module
agent: ask
---

# Plan a change before editing

Produce a proportionate, reviewable plan for the requested change. Do not edit
files while planning; the plan is the deliverable.

## Input

- The user-supplied argument describes the change. If it is empty or names
  only a file, ask one question that pins down the observable outcome.
- Optional context the user attached: issues, specs, diffs, or logs.

## Procedure

1. Load [kit-change-plan](../skills/kit-change-plan/SKILL.md) and follow its
   procedure; it owns plan sizing, slices, risks, and rollback.
2. Restate the outcome in one sentence a reviewer can check, plus explicit
   non-goals. Decide the plan size: a local edit gets a few lines.
3. Read the code before proposing structure. Trace callers, existing helpers,
   contracts, and owners of the affected area; cite `path:symbol` for each.
   Use [kit-context-onboarding](../skills/kit-context-onboarding/SKILL.md) if
   the area is unfamiliar.
4. Write binary acceptance criteria that include failure paths, following
   [acceptance criteria](../skills/kit-change-plan/references/acceptance-criteria.md).
   Map each criterion to the test that will prove it.
5. Split the work into vertical slices: a thin end-to-end tracer first, then
   slices ordered by risk. Each slice names its failing test, files, and the
   command that proves it is done.
6. List data, security, compatibility, and operational risks; turn every
   high-impact risk into an early slice, test, spike, or approval.
7. Give each slice an undo action and mark any point of no return (data
   migration, published contract, external side effect).
8. Record real prerequisites between slices; mark independent slices as
   safe to run in parallel instead of implying order.

## Acceptance gates

- [ ] Every criterion is observable and mapped to a named test or check.
- [ ] Every slice is independently verifiable and has a rollback.
- [ ] Claims about existing code cite a file you actually read.
- [ ] Open questions are listed, not silently assumed.

## Output

Return Markdown with these sections: Outcome and non-goals, Evidence read,
Acceptance criteria (table: criterion, proving test), Slices (numbered, with
files, test, done-command, rollback, depends-on), Risks, Open questions, and
the final verification command. Stop after the plan and wait for approval.
