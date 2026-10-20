# Integrate parallel results: merge order and conflict avoidance

Parallel work ends with one owner combining the results. Integration is where
hidden assumptions surface, so it gets its own plan and its own checks.

## Before anything merges

For every returned task, the integration owner checks:

1. **Scope**: the diff touches only the task's writable paths. Any extra file
   is either moved to the integration owner's list or rejected.
2. **Evidence**: the exact commands run, their results, and the negative case
   the task covered. Re-run the focused checks yourself; a reported pass is a
   claim, not evidence.
3. **Requests**: shared-file edits the worker could not make (lockfile,
   registry, changelog, generated code) are collected into one list.
4. **Assumptions**: anything the worker assumed about another task's output is
   compared with what that task actually produced.

## Merge order

Merge in dependency order, smallest blast radius first:

1. **Shared contracts** (schemas, interfaces, configuration keys) that others
   build on. These should already be in place from the decomposition step;
   anything still pending goes first.
2. **Providers** before consumers: the module that implements an interface
   before the module that calls it.
3. **Independent leaf tasks** in any order, one at a time.
4. **Integration-owned shared files**: dependency manifests and lockfiles,
   registries, generated clients, changelog. Regenerate rather than hand-merge
   generated files and lockfiles.
5. **Documentation** last, so it describes what was actually merged.

After each merge run the focused checks of everything merged so far. After the
last merge run the full completion gate once more. A failure that appears only
after combining two tasks is an integration defect: fix it on the integration
branch with its own regression test, not inside either worker's branch.

### Branch mechanics

- Integrate on a dedicated branch (for example `integrate/<topic>`) created
  from the same base the workers used, so the main branch stays releasable.
- Prefer merging each worker branch over rebasing it when several people may
  have fetched it; rebase only private branches.
- If the base moved during the work, update the integration branch from the
  base once, before merging worker branches, and resolve base conflicts there.
- Keep one commit or merge per task so a bad task can be reverted alone.

## Conflict avoidance

Most conflicts are predictable from the ownership table:

| Hot spot | Avoidance |
| --- | --- |
| Lockfiles and dependency manifests | only the integration owner edits them; regenerate after merging |
| Registries, route tables, `__init__.py` exports | integration owner appends entries from the collected requests |
| Changelog | one entry per task written by the owner at the end, or one fragment file per task |
| Formatter churn | each worker formats only owned paths; one final format by the owner |
| Generated code and snapshots | regenerate on the integration branch; never hand-merge |
| Renames and moves | schedule them alone, before or after the parallel phase, never during |

## Resolving a conflict that happens anyway

1. Identify the canonical contract each side was implementing. The correct
   resolution satisfies the contract and both tasks' tests, not whichever
   patch is larger or newer.
2. If both sides changed behavior, the decomposition was wrong. Stop, decide
   the intended behavior with the requester, and add a test that pins it.
3. Re-run both tasks' focused checks after resolving.
4. Record the conflict cause in the hand-off so the next decomposition avoids
   it.

## Abandoning or replacing a task

If a task returns incomplete, wrong, or out of scope:

- Do not merge partial work "to be fixed later". Either finish it on its own
  branch or drop it entirely.
- Report the dropped outcome and its check explicitly; never let it vanish from
  the final summary.
- Stop only processes and worktrees you own. Another person's or agent's
  worktree is not yours to clean up.

## Final hand-off

The integration owner reports:

- Each task: outcome, merged commit or diff, checks re-run, limitations.
- Shared-file edits applied on behalf of tasks.
- Integration defects found and their regression tests.
- The final completion gate command and result.
- Worktrees and branches that remain, with their cleanup commands.

## Sources

- [git-merge](https://git-scm.com/docs/git-merge)
- [git-rebase: recovering from upstream rebase](https://git-scm.com/docs/git-rebase#_recovering_from_upstream_rebase)
- [git-worktree](https://git-scm.com/docs/git-worktree)
- [GitHub: about merge methods](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github)
