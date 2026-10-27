# The improvement loop

Reusable guidance lives in one repository. Projects consume it; they do not
fork it. A problem found in any project becomes a small reviewed change to the
source, and every project gets it on its next update.

## Roles

| Role | Does | Never does |
| --- | --- | --- |
| Agent in the consuming project | Traces the file, reproduces synthetically, edits the kit checkout, runs checks, commits on request | Edits the installed copy, pushes without approval, touches other repositories |
| Owner | Approves the push and the merge, tags releases, changes repository settings | Skips the required checks |
| Required checks | Block a merge until the kit's own gates pass | Are weakened to merge a change |
| Separate agent identity and branch ruleset | Keep the agent a write-role account whose pull requests need the owner's approval before merging | Let the agent approve or bypass its own change |

## Flow

1. Notice the problem in a consuming project and classify it with
   [change classes](change-classes.md).
2. Trace the installed file to its package (`apm find <path> --source`).
3. Open the kit checkout as an additional working directory:
   - VS Code: **File > Add Folder to Workspace**.
   - Claude Code: `claude --add-dir <path>` or `/add-dir <path>`.
   - GitHub Copilot CLI: `copilot --add-dir <path>` or `/add-dir <path>`;
     adding a directory also loads its `.github/skills` and `.github/agents` as
     trusted configuration, so add only the owner's own checkout.
4. Edit the source, run `task verify` in the checkout, commit on a branch.
5. After approval, push the branch and open a pull request with auto-merge.
6. When it merges, refresh each project: `apm update` (project scope) or
   `apm update -g` (user scope).

## Rollback

- Revert the merge commit through a pull request; consumers pick it up on the
  next update.
- To hold one project back, pin the dependency to a known commit or tag in its
  `apm.yml` and reinstall; do not edit `apm.lock.yaml` by hand.
- Never replace published bytes of a tagged release; publish a corrected one.

## Limits

- APM has no live link between a checkout and an installed copy. After a merge
  the consumer must update to see the change.
- `apm find` traces files for project installs; for user-level or composed
  installs, identify the package from the skill name.
- Prefix permission rules and terminal approvals are speed bumps. The boundary
  is hosted: an agent identity without review or admin rights, and a ruleset that
  requires the owner's approval.
- A file test does not prove that a host session follows the new guidance;
  say which host and version you observed it in.
