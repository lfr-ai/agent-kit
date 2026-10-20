---
name: kit-parallel-work
description: Use when dividing independent analysis or edits while retaining clear ownership and integration checks.
license: MIT
---

# Parallelize only independent work

## Procedure

1. Write the outcome as a short list of observable checks. Decide whether the
   work is worth splitting at all: lookups, small edits and single continuous
   traces stay with one owner.
2. Find seams and pin shared contracts before any worker starts, using
   [decomposition and ownership](references/decomposition.md). Assign every
   check to exactly one task.
3. Fill the ownership table: disjoint writable paths, read-only inputs, real
   prerequisites, and one integration owner for lockfiles, manifests,
   registries, generated code and the changelog.
4. Brief each worker with a [bounded assignment](assets/assignment.md.template)
   carrying the same prohibitions (no remote, global, deployment or credential
   actions without operator approval). Workers never delegate further.
5. When writers run concurrently and the operator has approved branches, give
   each its own worktree as described in [worktrees](references/worktrees.md).
   Plan with the [worktree planner](assets/new_worktree.py), which only prints
   Git commands until it is re-run with `--execute`.
6. Run read-only research and disjoint writers in parallel; hold back any task
   whose prerequisite is unfinished.
7. Review each returned diff against its writable paths and re-run its focused
   checks before accepting it.
8. Integrate in dependency order and avoid predictable conflicts following
   [integration](references/integration.md): contracts, providers, consumers,
   leaf tasks, shared files, then documentation, checking after each merge.
9. Resolve conflicts by the canonical contract and both tasks' tests, never by
   choosing the larger patch. Stop and re-plan if a new shared dependency
   invalidates the split.
10. Run the completion gate after the last merge and report each task's outcome,
    integration defects, remaining worktrees and their cleanup commands.

The [coordination gates](references/guide.md) summarize the rules in one page.

## Acceptance gates

- Every check in the outcome list has exactly one owning task.
- Writable path sets are disjoint, including registries, exports and lockfiles.
- No worker edited a shared contract or another task's paths.
- Each accepted task has re-run evidence, not only a reported pass.
- The completion gate passed after all merges, on the integration branch.
- Dropped or incomplete tasks are reported, and no worktree, branch or process
  owned by someone else was removed.
- Prompt-level scope is not described as isolation; permissions and worktrees
  are named as the actual boundaries.
