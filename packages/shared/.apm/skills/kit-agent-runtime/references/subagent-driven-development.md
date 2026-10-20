# Subagent-driven development

A coordinator splits a change into bounded tasks, sends each to a worker with its
own context, and integrates verified results. Delegation costs model usage and
coordination, so use it only when a task needs separate context or can run in
parallel without conflicts. A lookup or a small edit stays with the coordinator.

## Roles and contracts

| Role | Owns | Must not |
| --- | --- | --- |
| Coordinator | Plan, task boundaries, integration, final verification, handoff to the requester | Delegate trivial lookups, run overlapping workers, accept claims without evidence |
| Read-only worker (researcher, planner, architect, reviewers) | One question or one review scope | Edit, run commands, or delegate |
| Implementer worker | One task inside its owned paths, plus the tests and evidence for it | Touch other paths, publish, change global settings, or delegate |

Workers are stateless between invocations in several runtimes: the VS Code Local
harness, for example, does not pass conversation history to a subagent and does
not allow follow-up messages to the same invocation. Every assignment must
therefore be self-contained.

The native role definitions in [agents.json](../assets/agents.json) encode these
contracts; see [native roles](native-roles.md).

## Assignment contract

Every assignment from coordinator to worker contains:

1. **Outcome**: one observable result and why it matters.
2. **Context**: relevant paths, decisions already made, and conventions to follow.
3. **Owned paths**: the exact files or directories the worker may change. Read-only
   workers get a search scope instead.
4. **Forbidden actions**: publication, live resources, global settings, secrets,
   and every path outside the owned set.
5. **Acceptance criteria**: numbered, each with the command or observation that proves it.
6. **Stop condition**: when to return, including what to do when blocked.
7. **Return format**: the [handoff template](../assets/handoff.md.template) for
   implementers, or a findings list for reviewers.

Use the [task template](../assets/task.md.template) for the outcome and scope part.

## Procedure

1. **Size.** Count the files and decisions involved. Fewer than a handful of direct
   reads and edits means no delegation.
2. **Plan.** Get acceptance criteria and vertical tasks. Each task delivers one
   testable behavior end to end.
3. **Check the plan.** Confirm placement, dependency direction, reuse, and that no
   task edits generated output instead of its source.
4. **Partition.** Assign disjoint owned paths. Tasks that share a file run in
   sequence; only independent tasks run in parallel.
5. **Dispatch.** Send self-contained assignments. Do not let workers start further
   workers.
6. **Collect.** Each implementer returns a handoff and a review package built from
   its actual diff and verification output.
7. **Review.** Route each package to the reviewer that matches its risk:
   correctness for logic, coupling for interfaces and module boundaries, security
   for inputs, identity, and secrets.
8. **Resolve.** Fix small findings directly; send a narrower follow-up assignment for
   larger ones. Do not re-review unrelated work.
9. **Integrate and verify.** After the last edit, the coordinator runs the
   repository verification commands itself. Earlier worker output does not count.
10. **Hand off.** Report outcome, changed paths, review results, exact commands and
    results, limitations, and next actions.

## Review packages

[review_package.py](../assets/review_package.py) turns evidence into a reviewer-ready
Markdown report and acts as a gate:

```text
git diff --no-color > change.diff
python review_package.py --diff change.diff --evidence evidence.json \
  --allow src/orders --allow tests/unit/orders --output review.md
```

The evidence file follows
[review-evidence.json.template](../assets/review-evidence.json.template): task,
worker, summary, acceptance criteria with status and evidence, commands with exit
code and summary, limitations, and follow-up items. The script parses git and plain
unified diffs, including renames, additions, deletions, and binary markers.

The gate fails (exit `1`) when the diff is empty, a changed or renamed-from path is
outside every `--allow` prefix, no verification command was recorded, a command
has a non-zero exit code, or an acceptance criterion is `unmet` or `partial`.
Unreadable or invalid inputs exit `2`. Output is deterministic: it includes a
SHA-256 of the diff instead of a timestamp, and `--output` refuses to overwrite an
existing file without `--force`.

The script packages evidence; it does not run git or the commands, so a reviewer
should spot-check that recorded commands match the diff.

## Handoff format

Implementer handoffs use [handoff.md.template](../assets/handoff.md.template):
assignment echo, status, changed paths taken from the diff, acceptance table,
verification table run after the final edit, open items, and the review package
command with its gate status. Read-only workers return the answer, evidence with
paths, and unresolved facts.

Rules for every handoff:

- Paths come from the diff, not memory.
- Commands are copied exactly, with their exit codes.
- Assumptions, unsupported cases, and blockers are listed, not hidden in prose.
- Nothing is claimed about a native runtime that was not exercised.

## Failure handling

- A worker that reports a blocker gets a re-plan, not a retry with the same prompt.
- Two workers that need the same file are merged into one task or sequenced.
- A reviewer finding without a path and scenario is returned for evidence.
- If a worker returns no useful output, the coordinator continues directly rather
  than relaunching the same assignment.

## Sources

- [VS Code subagents](https://code.visualstudio.com/docs/agents/subagents)
- [VS Code custom agents](https://code.visualstudio.com/docs/agent-customization/custom-agents)
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [GitHub Copilot custom agents](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/create-custom-agents)
- [Anthropic: building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [git diff](https://git-scm.com/docs/git-diff)
