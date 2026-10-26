---
description: Self-review the finished change against its rules and acceptance criteria, iterate within a loop budget, and record durable lessons.
argument-hint: Optional loop budget or scope, e.g. "budget 2" or a changed path
agent: agent
---

# Run the feedback loop on a finished change

Review your own change before handing it off: rules first, deterministic
checks next, then judgment. Iterate only on findings that matter, and stop
when the budget is spent.

## Input

- The working-tree changes and the acceptance criteria of the task.
- The user-supplied argument may set the loop budget (default three
  iterations) or narrow the scope to a path.

## Procedure

1. Load [kit-feedback-loop](../skills/kit-feedback-loop/SKILL.md) and follow
   its procedure; it owns the loop budget and the iterate-or-stop rules.
2. Start an [iteration log](../skills/kit-feedback-loop/assets/iteration-log.md.template)
   with the budget and the early-stop condition.
3. Re-read the policy, the instructions whose scope matches each changed
   path, and the skills used. List the rules to check.
4. Run the project's declared formatter check, linter, type checker,
   convention checks and focused tests on the changed files. Use
   [kit-verify-change](../skills/kit-verify-change/SKILL.md) for the full gate.
5. Inspect what checkers cannot see with the
   [review checklist](../skills/kit-feedback-loop/assets/review-checklist.md.template),
   citing `path:line` for each finding.
6. Score the change with the [rubric](../skills/kit-feedback-loop/assets/rubric.md.template)
   and decide to iterate or stop. Fix the highest-severity finding first.
7. After the last iteration, re-run the checks and record durable, evidenced
   lessons through [kit-project-memory](../skills/kit-project-memory/SKILL.md).
8. Never weaken a check, threshold or assertion to make the loop end.

## Acceptance gates

- [ ] The budget was set first and not exceeded.
- [ ] Checks ran after the last edit, with exact commands and results.
- [ ] Every acceptance criterion has a status and evidence.
- [ ] Zero lessons is reported as such; nothing transient was stored.

## Output

A table of acceptance criteria (criterion, status, evidence), the checks run
with results, iterations used and the stop reason, remaining findings by
severity, and lessons recorded or "none".
