---
description: Archive a verified spec change by merging its requirements into the living spec, moving the folder, and proving both still agree.
argument-hint: Change folder path or identifier, or "all verified"
agent: agent
---

# Archive a verified spec change

Make the living spec the single source of truth for what the change delivered,
then retire the change folder without losing history.

## Input

- The user-supplied argument is the change folder path or identifier. The
  phrase "all verified" archives every change whose result is pass, one at a
  time, in merge order.

## Procedure

1. Load [kit-spec-workflow](../skills/kit-spec-workflow/SKILL.md) and follow
   the [archive stage](../skills/kit-spec-workflow/references/stage-archive.md).
2. Check entry criteria: status verified, result pass, owner acceptance
   recorded, and the change merged or released according to project policy.
   Refuse to archive early.
3. Identify the living spec file for each affected capability; create one only
   when the capability has none.
4. Merge each requirement by its change kind: add new requirements, replace
   modified ones in place, and delete removed ones. Keep requirement
   identifiers stable.
5. Read the merged living spec top to bottom and resolve contradictions or
   duplicates. If another change modified the same requirement since this one
   was specified, stop and run the sync operation from
   [operations](../skills/kit-spec-workflow/references/operations.md).
6. Set the status to archived in the proposal.
7. Move the folder to the archive location with a dated name, preserving file
   history where the project uses version control.
8. Run the skill's checker on the archived folder; it must still pass.
9. Update links that pointed at the active folder.
10. When archiving several changes, repeat the procedure per change and re-read
    the living spec after each merge.

## Acceptance gates

- [ ] The living spec contains every active requirement in its final wording.
- [ ] The archived folder is complete and passes the checker.
- [ ] No active folder with the same identifier remains.
- [ ] No unverified change was archived.

## Output

Per change: living spec files updated (requirements added, modified,
removed), the archive path, checker result, and links updated. List any change
that was skipped and why.
