---
description: Implement a planned spec change task by task, test first, ticking each box only with recorded evidence and resuming cleanly after interruptions.
argument-hint: Change folder path or identifier
agent: agent
---

# Apply a planned spec change

Implement the tasks of one planned change in order, keeping the change folder
an accurate record of what was done and proven.

## Input

- The user-supplied argument is the change folder path or identifier. When it
  is empty, list open change folders with status planned or in progress and
  ask which to apply.

## Procedure

1. Load [kit-spec-workflow](../skills/kit-spec-workflow/SKILL.md) and follow
   the [apply stage](../skills/kit-spec-workflow/references/stage-apply.md).
2. Check entry criteria: the checker passes with `--trace`, the working tree
   is clean, and the baseline test suite passes. Report and stop otherwise.
3. If work was interrupted, follow the continue operation in
   [operations](../skills/kit-spec-workflow/references/operations.md): re-run
   the evidence command of the last ticked task and clear its box if it fails.
4. Pick the first open task whose prerequisites are ticked.
5. Re-read the requirements and scenarios it cites. If a scenario is wrong or
   ambiguous, stop and use the update operation; do not reinterpret approved
   scope silently.
6. Write or extend the test that proves the cited scenario and watch it fail
   for the intended reason. Apply the shared `kit-test-first` skill when it is
   installed.
7. Implement the smallest change that makes it pass. Keep unrelated cleanups
   out of the task.
8. Run the focused tests, then the affected package's suite and linters.
9. Tick the box and append the evidence command and result inline.
10. Record any design deviation in the change folder as it happens.
11. Repeat until every task is ticked or explicitly deferred to a new change.

## Acceptance gates

- [ ] Every ticked box carries evidence that was produced in this session.
- [ ] Deviations from the design are recorded with a reason.
- [ ] Deferred tasks name the follow-up change.
- [ ] Focused and package suites pass; the checker still passes.

## Output

Tasks completed with evidence, tasks deferred with destinations, deviations,
files changed, and commands run with results. Offer the `kit-spec-verify`
prompt next.
