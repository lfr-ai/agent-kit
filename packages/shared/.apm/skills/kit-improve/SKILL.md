---
name: kit-improve
description: Use when an installed kit capability misbehaves or needs a lasting fix in the kit source, not a local copy.
license: MIT
---

# Improve the kit at its source

The installed copy is generated; a fix kept there is overwritten and never
reaches your other projects. Change the owning source once, review it, and let
every project pull it. Use [change classes](references/change-classes.md) to
decide whether the change is reusable at all.

## Procedure

1. State the problem or improvement in one sentence and name the installed file
   that shows it. If the fact is true only for this project (its stack,
   commands, owners), put it in this project's own instructions and stop here.
2. Find the owning package: run `apm find <installed-path> --source`. Record the
   package, its origin and the locked commit from `apm.lock.yaml`. If APM has no
   record (user-level or composed install), ask the user which package owns it;
   skill names are unique `kit-<topic>` identifiers.
3. Locate the kit checkout by asking the user for its path or reading
   `AGENT_KIT_DIR`; never search the disk or clone one unprompted. Run
   `git -C <checkout> remote get-url origin` and `git -C <checkout> status --short`.
   Continue only when the origin equals the recorded origin and the tree is
   clean; otherwise stop and report. Without a checkout, draft the
   [change record](assets/capability-change.md.template) for an issue and stop.
4. Reproduce the behavior with a synthetic example, following
   [synthetic examples](references/synthetic-examples.md). Nothing private from
   this project may enter the kit: no code, names, paths, hosts or secrets.
5. Open the checkout as an additional working directory in your host and edit
   only its source: `.apm/` or `packages/*/.apm/`. Never edit `apm_modules/`,
   `.github/skills/`, `.claude/skills/`, `.agents/skills/` or any generated
   file. Make the smallest change that fixes the cause; keep one outcome per
   pull request.
6. Follow the kit's own `AGENTS.md`, `PROJECT.md` and authoring skill for the
   file type. Record the failing prompt and the expected behavior in the pull
   request body using the [pull request template](assets/pull-request.md.template).
7. Run the checks the kit names for the change from inside the checkout, ending
   with `task verify`, and read the result; do not paraphrase it.
8. Create a `fix/<capability>` or `feat/<capability>` branch and commit with a
   Conventional Commit message. This step applies only to a change the user
   asked for in this session.
9. Show the user the exact push and pull request commands and run them only
   after approval:
   `git push -u origin <branch>`, `gh pr create --fill`, then
   `gh pr merge --auto --squash` once the user also approves merging.
10. Report the pull request link and the checks it must pass. After it merges,
    tell the user to refresh with `apm update` (project) or `apm update -g`
    (user level), then confirm the installed file changed.

## Boundaries

- This skill grants version-control commands only inside the verified kit
  checkout. Every other repository keeps its own rules.
- Never push or merge to the default branch, force-push, rewrite pushed history,
  tag, create a release, change repository settings or touch credentials.
- Stop and report when the origin differs, the tree is dirty, a push or check
  is rejected, or the change would need another repository.

## Acceptance gates

- The owning source, not an installed copy, changed.
- The problem and expected behavior are recorded with a synthetic example.
- `task verify` passed in the checkout and its output was read.
- A human approved the push and the merge; nothing reached the default branch
  directly.
- The loop, rollback and limits in [the improvement loop](references/loop.md)
  were respected.
