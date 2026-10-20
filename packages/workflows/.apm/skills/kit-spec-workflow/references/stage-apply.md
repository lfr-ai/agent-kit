# Stage 5: Apply

Apply implements the plan one task at a time. The task list is the progress
record: a ticked box is a claim that the task's evidence exists right now.

## Entry criteria

- `Status: planned`, checker passes with `--trace`.
- The working tree is clean and the baseline test suite passes, so new
  failures can be attributed to this change.

## Loop per task

1. Pick the first open task whose prerequisites are ticked. Set
   `Status: applying` when starting the first one.
2. Re-read the requirements and scenarios it cites. If a scenario is
   ambiguous, stop and clarify it in `requirements.md` before writing code;
   record the clarification in the review thread.
3. Write or extend the test that will prove the cited scenario. Run it and
   confirm it fails for the expected reason.
4. Implement the smallest change that makes it pass. Keep unrelated cleanups
   out of the diff; note them as follow-up candidates instead.
5. Run the focused tests, then the affected package's suite and linters.
6. Tick the box and append the evidence inline, for example
   `- [x] 2.1 Stream rows to CSV (REQ-001) - tests/test_export.py::test_month`.
7. Commit or checkpoint according to the project's conventions, one task per
   reviewable unit where practical.

## Handling surprises

| Surprise | Action |
| --- | --- |
| A task is bigger than expected | Split it in `tasks.md` before continuing |
| A requirement is wrong or incomplete | Pause, run the update operation, get owner acceptance |
| The design does not work | Record the deviation in `design.md` with the reason, then continue |
| Work outside scope is needed | Add a follow-up note; do not widen the change silently |
| A task becomes unnecessary | Strike it through with a reason and tick it; keep the line |

The update operation is described in [operations](operations.md).

## Exit criteria

- Every box is ticked with evidence, or explicitly deferred: moved to a new
  change folder and referenced from a note in `tasks.md`.
- Focused and package test suites pass locally.
- Design deviations are recorded.

## Acceptance gate

The checker passes and a reviewer has seen each task's diff and evidence.
Continue with [verify](stage-verify.md).

## Anti-patterns

- Ticking boxes in bulk at the end.
- Turning a failing scenario green by changing the scenario without an update.
- Mixing refactors into feature tasks so the review cannot isolate behavior.
- Leaving debug flags, skipped tests or placeholder markers behind.

## Sources

- [pytest: How to invoke pytest](https://docs.pytest.org/en/stable/how-to/usage.html)
- [Git commit documentation](https://git-scm.com/docs/git-commit)
