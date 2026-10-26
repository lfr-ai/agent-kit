---
name: kit-subagent-delivery
description: Use when delegating implementation to subagents with owned paths, handoff checks and coordinator verification.
license: MIT
---

# Deliver a change through subagents

## Procedure

1. Decide whether to delegate with the
   [delegation table](references/delivery.md#delegate-or-do-directly). Lookups,
   single traces and edits that take a handful of direct steps stay with the
   coordinator.
2. Write acceptance criteria first, then decompose into vertical tasks with
   disjoint owned paths. One file has one owner; shared contracts, lockfiles,
   registries and the changelog belong to the coordinator. Seam finding and
   worktree isolation are owned by the `kit-parallel-work` skill.
3. Order tasks: run independent tasks in parallel and dependent ones in
   sequence, following [parallel or sequential](references/delivery.md#parallel-or-sequential).
4. Write one [assignment package](assets/assignment.md.template) per task:
   outcome, read-first context, owned paths, forbidden actions, acceptance
   checks with exact commands, stop condition, context budget and the handoff
   format. Assignments are self-contained; workers may not see the
   conversation.
5. Keep each worker's context small: link files to read instead of pasting
   them, select only the skills the task uses, and state what not to load.
   Worker roles, tiers and runtime contracts are owned by the
   `kit-agent-runtime` skill.
6. Forbid nested delegation: workers never start other workers, and the
   coordinator never relaunches the same objective after an empty or failed
   result. Re-plan narrower or do it directly.
7. Collect each [handoff](assets/handoff.md.template) and validate it with
   [`check_handoff.py`](assets/check_handoff.py), for example
   `python check_handoff.py handoffs/task-1.md`. It requires changed paths,
   commands with results, and limitations, and rejects unfilled placeholders.
8. Compare the reported paths with the actual diff; reject edits outside the
   owned paths. Route each change to a reviewer by risk with the
   [review routing table](references/delivery.md#review-routing).
9. Integrate in dependency order, resolve findings (small ones directly,
   large ones as a narrower follow-up assignment), then run the full
   verification yourself after the last edit. Worker results do not count as
   final evidence.
10. Report to the requester: outcome per task, changed paths, review results,
    exact commands with results, limitations and next actions.

Failure handling and anti-patterns are in the [delivery reference](references/delivery.md).

## Acceptance gates

- Every acceptance criterion has exactly one owning task, and owned path sets
  are disjoint.
- Every assignment states outcome, owned paths, forbidden actions, checks,
  stop condition and handoff format, and was sent without relying on chat
  history.
- Every handoff passes `check_handoff.py`, and its paths match the diff.
- No worker started another worker; no objective was relaunched unchanged.
- Each change was reviewed by the reviewer matching its risk, and findings
  are resolved or reported.
- The coordinator ran the declared verification after the last edit and
  reported exact results.
