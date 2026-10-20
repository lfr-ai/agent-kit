# Parallel work without shared-write races

## Split by owned outcome

Delegate only work that needs a meaningful independent context. A small lookup
or one continuous execution trace stays with its owner. Define writable paths,
read-only contracts, prerequisites, forbidden actions, exact checks and stop
conditions. Workers do not recursively delegate.

One coordinator owns shared schemas, dependency manifests, generated output and
final integration. Do not run multiple formatters or generators on the same
tree. Read-only research can run alongside disjoint edits; a consumer of an
unfinished interface must wait.

For operator-approved worktrees, retain the exact worktree paths and ownership.
Creating a worktree, branch or commit is a version-control operation, not an
implicit consequence of asking an agent for help.

## Quality gates

- Assignments have non-overlapping writable paths and explicit shared owners.
- Each worker returns changed paths, observable results, commands and limitations.
- Results are integrated only after prerequisites and contract checks pass.
- The coordinator verifies cross-boundary behavior after all independent work.
- No worker claims native isolation merely because its prompt limits scope.

## Failure and recovery

If a worker needs another owner's file, stop that edit and return the needed
contract change. If writes conflict, compare intended behavior and tests rather
than accepting the larger patch. Cancel only known owned processes, preserve
other users' work, and report incomplete results instead of silently dropping them.

Sources: [Claude subagents](https://code.claude.com/docs/en/sub-agents),
[Git worktrees](https://git-scm.com/docs/git-worktree).
