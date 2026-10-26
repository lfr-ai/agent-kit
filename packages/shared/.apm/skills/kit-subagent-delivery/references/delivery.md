# Delivery through subagents: decisions and failure handling

Reviewed: 2026-10-23.

A subagent runs in its own context window. That isolation is the benefit
(the coordinator's context stays small and focused) and the cost (the worker
knows only what the assignment says, and every launch spends tokens and
time). Delegate when isolation or parallelism pays for those costs.

Role contracts, native role definitions and the review package script are
owned by the `kit-agent-runtime` skill. Seam finding, worktrees and merge
order are owned by the `kit-parallel-work` skill. This reference covers the
coordinator's delivery decisions.

## Delegate or do directly

| Situation | Decision | Reason |
| --- | --- | --- |
| Answer needs a few searches or file reads | direct | launch cost exceeds the work |
| One continuous trace across files | direct | splitting loses the thread |
| Edit fits in about five direct tool calls | direct | delegation adds latency and review |
| Independent subsystems, each needing deep reading | delegate | separate contexts stay focused |
| Broad research whose raw output would flood the coordinator | delegate to a read-only worker | only the summary returns |
| Independent edits with disjoint paths and clear checks | delegate in parallel | wall-clock time drops |
| Work needs decisions only the requester can make | neither; ask or report | a worker cannot resolve it |
| Destructive, remote or credentialed action | neither by default | needs explicit operator approval |

## Decomposition rules

- Cut by observable outcome (vertical task), not by layer, unless a contract
  must be pinned first.
- Give every task owned paths that no other task writes. A shared file is
  either owned by one task or reserved for the coordinator.
- Pin shared contracts (schemas, interfaces, names) before workers start, in
  the assignment text or a coordinator-owned file.
- Put generated outputs, lockfiles, registries, catalogs and the changelog in
  the coordinator's integration step.
- Each task carries its own acceptance checks; a check nobody owns is a gap.

## Parallel or sequential

| Relationship between tasks | Run |
| --- | --- |
| Disjoint paths, no data or contract dependency | parallel |
| B consumes a contract A defines | A first, or pin the contract and run both |
| Both need the same file | merge into one task, or sequence them |
| B's checks need A's output | sequence |
| Read-only research feeding a later edit | research first, then the edit |
| Uncertain dependency | sequence; parallelism is an optimization, not a default |

## Context isolation and budget

- The assignment is the worker's whole world. State the outcome, the files to
  read first, decisions already made, and conventions that apply.
- Link files instead of pasting them; paste only the few lines that pin a
  contract.
- Name the skills to load and the ones to skip. A worker that loads the whole
  library spends its context before it starts.
- Bound the return: a handoff under a fixed number of lines, findings with
  paths, no transcripts or full logs.
- Ask for evidence, not narration: commands with results, paths from the
  diff, limitations.

## Review routing

| Change risk | Reviewer focus |
| --- | --- |
| Logic, algorithms, edge cases | correctness |
| Public interfaces, module boundaries, dependency direction | coupling and architecture |
| Input handling, identity, secrets, permissions | security |
| Infrastructure, CI, containers | delivery and least privilege |
| Documentation only | accuracy against the code; no deep review |
| Generated output | regenerate from source; do not review by hand |

Send each reviewer the diff, the assignment, the handoff and the check
results. A finding without a path and a failing scenario goes back for
evidence.

## Integration and final verification

1. Check each handoff with `check_handoff.py`, then compare its changed paths
   with the diff.
2. Re-run each task's focused checks; a reported pass is a claim until re-run.
3. Merge in dependency order; regenerate derived files from their sources.
4. Run the repository's full declared verification after the last edit.
5. Report per task: accepted, fixed, deferred or dropped, with evidence.

## Failure handling

| Event | Response |
| --- | --- |
| Worker returns nothing useful | continue directly; do not relaunch the same assignment |
| Worker reports a blocker | re-plan: narrower scope, missing input supplied, or escalate |
| Worker edited outside its owned paths | reject those edits; re-assign or do them in integration |
| Two workers need the same file | stop one; merge the tasks or sequence them |
| Handoff fails the checker | return it once for the missing sections; then treat claims as unverified |
| Checks pass for the worker but fail after integration | the integration step owns the fix; find the coupling |
| A worker wants to delegate further | not allowed; it returns a proposal instead |

## Anti-patterns

- Nested fleets: workers starting workers multiply cost and lose ownership.
- Relaunching the same objective after a poor result instead of re-planning.
- Delegating a lookup and waiting idle for it.
- Splitting one continuous trace across workers.
- Accepting "tests pass" without the command and its output.
- Letting two workers edit a lockfile or registry in parallel.

## Primary sources

- [VS Code subagents](https://code.visualstudio.com/docs/agents/subagents)
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [GitHub Copilot custom agents](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/create-custom-agents)
- [Anthropic: building effective agents (orchestrator-workers)](https://www.anthropic.com/engineering/building-effective-agents)
- [Anthropic: effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
