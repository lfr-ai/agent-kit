# Stage 7: Archive

Archive folds the verified requirements into the living specification and
freezes the change folder as history. After archival the living spec, not the
change folder, is the source of truth for current behavior.

## Entry criteria

- `Status: verified`, `Result: pass`, owner acceptance recorded.
- The change is merged or released according to project policy. Archiving an
  unmerged change creates a living spec that describes behavior nobody has.

## Activities

1. Identify the living spec file for each affected capability. Create one if
   the capability is new, using the same requirement grammar.
2. Merge requirements by `Change:` kind:
   - `add`: append the requirement and its scenarios. Renumber only if the
     identifier collides, and note the original identifier in parentheses.
   - `modify`: replace the existing requirement's statement and scenarios;
     drop the `Previously:` line.
   - `remove`: delete the requirement from the living spec; keep the reason in
     the archived change only.
3. Read the merged living spec top to bottom. Remove contradictions and
   duplicated scenarios introduced by the merge.
4. Set `Status: archived` in `proposal.md`.
5. Move the folder to `<changes-root>/archive/<YYYY-MM-DD>-<change-id>/` using
   the merge or release date.
6. Run the checker on the archived folder; it must still pass, which proves no
   open tasks or failing verification were archived.
7. Update links that pointed at the active folder (tickets, docs, release
   notes) to the archive path.

## Conflict handling

When another change modified the same requirement after this change was
specified, do not overwrite it. Reconcile the two statements, add a scenario
for the combined behavior, and record the reconciliation in the archived
`verification.md` notes. If the behaviors are incompatible, stop and run the
update operation on the later change.

## Exit criteria

- The living spec contains every active requirement of the change in its final
  wording, and none of the removed ones.
- The archived folder is complete and passes the checker.
- No active folder with the same identifier remains.

## Acceptance gate

A reviewer diffs the living spec before and after the merge and finds only the
changes described in `requirements.md`. Archival is a documentation commit; it
must not carry code changes.

## Anti-patterns

- Archiving to "clean up" unfinished work; abandoned changes are closed with a
  note, not archived as if delivered.
- Copying the change's `requirements.md` wholesale over the living spec.
- Renaming identifiers in the archive after the fact.

## Sources

- [Git mv documentation](https://git-scm.com/docs/git-mv)
- [ISO 8601 date and time format](https://www.iso.org/iso-8601-date-and-time-format.html)
