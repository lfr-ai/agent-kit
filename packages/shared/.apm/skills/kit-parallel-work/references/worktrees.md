# One worktree per agent

A Git worktree is an additional working directory attached to the same
repository. Each worktree has its own checked-out branch, index and files, and
shares the object database, refs and configuration with the main working tree.
Giving every concurrently writing agent its own worktree means formatters,
generators, test caches and half-finished edits cannot collide on disk.

Creating worktrees and branches is a version-control operation. Do it only
inside a workflow the operator has approved; an agent asked to "help in
parallel" has not thereby been authorized to create branches.

## When a worktree is worth it

| Situation | Use |
| --- | --- |
| Read-only research, review, or search | the main tree; no worktree |
| One agent, one change | the main tree or a single feature branch |
| Several agents writing disjoint paths at the same time | one worktree per writing agent |
| Agents that must run formatters, generators or full test suites concurrently | one worktree each, always |
| Experiments that may be thrown away | a worktree on a throwaway branch |

## Plan the worktree

The [worktree planner](../assets/new_worktree.py) validates a branch name, a
base commit-ish and a target directory, then **prints** the Git commands it
would run. Nothing changes until it is re-run with `--execute`.

```text
python new_worktree.py --branch agent/orders-api --base main
# Dry run. Review, then re-run with --execute to apply:
git -C /work/shop check-ref-format --branch agent/orders-api
git -C /work/shop rev-parse --verify --quiet 'main^{commit}'
git -C /work/shop worktree add -b agent/orders-api -- /work/shop-agent-orders-api main
# Cleanup after the branch is merged or abandoned:
# git -C /work/shop worktree remove -- /work/shop-agent-orders-api
# git -C /work/shop branch --delete agent/orders-api
```

What the planner enforces:

- Branch names follow `git check-ref-format` rules: no spaces, control
  characters, `~ ^ : ? * [ \`, `..`, `@{`, `//`, components starting with `.`,
  or names ending in `/`, `.` or `.lock`. A leading `-` is rejected so a name
  can never be read as an option.
- The base may use ancestry suffixes (`HEAD~2`, `main^`) but follows the same
  rules otherwise and is verified to resolve to a commit before anything is
  created.
- The default directory is a sibling of the repository named
  `<repository>-<branch-slug>`. The path must be outside the current working
  tree and must not exist, or must be an empty directory.
- Every command is a fixed argument vector run without a shell; `--` separates
  options from the path and base. Execution stops at the first failing command.
- `--repo` selects the repository; relative `--path` values resolve against the
  current directory.

The printed lines use POSIX quoting for review. On Windows copy the paths with
the quoting your shell expects, or use `--execute`.

Recommended naming: `agent/<topic>` for agent branches, one topic per branch,
so `git branch --list 'agent/*'` shows every outstanding parallel task.

## Work inside the worktree

1. Bootstrap the environment inside the worktree with the repository's locked
   install command. Virtual environments and dependency folders are per
   worktree; never point one worktree at another's environment.
2. Keep generated output, caches and build folders inside the worktree.
   Absolute paths in tool configuration break this isolation; fix them in the
   owning configuration rather than working around them.
3. Run the focused checks named in the assignment inside the worktree, then the
   repository's completion gate before handing back.
4. Commit only when the operator workflow allows it; otherwise hand back the
   diff and the evidence.

## Remove the worktree

After the branch is merged or abandoned:

1. `git worktree remove <path>` refuses to delete a worktree with uncommitted
   or untracked changes. Inspect them first; use `--force` only after the
   owner confirms the changes are disposable.
2. `git branch --delete <branch>` refuses an unmerged branch; `-D` discards
   commits and needs the same confirmation.
3. `git worktree prune` removes administrative records for worktree directories
   that were deleted by hand. `git worktree list --porcelain` shows what
   remains, including `locked` and `prunable` entries.
4. A worktree on removable or network storage can be protected from pruning
   with `git worktree lock --reason "<why>"`; unlock it before removal.

## Limits

- A branch can be checked out in only one worktree at a time. Two agents cannot
  share a branch; give each its own and integrate through merges.
- Hooks, configuration and refs are shared. A hook installed for one worktree
  runs in all of them, and a branch deleted in one is gone in all.
- Submodules need their own initialization in each worktree.
- Worktree isolation is a file-system convention, not a sandbox. An agent in
  one worktree can still read or write any path its permissions allow; the
  assignment's writable paths and the host's permission settings remain the
  real boundary.

## Sources

- [git-worktree](https://git-scm.com/docs/git-worktree)
- [git-check-ref-format](https://git-scm.com/docs/git-check-ref-format)
- [git-rev-parse: specifying revisions](https://git-scm.com/docs/gitrevisions)
- [Python subprocess security considerations](https://docs.python.org/3/library/subprocess.html#security-considerations)
