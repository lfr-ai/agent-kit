# Maintenance operations

These operations keep changes and living specs consistent when reality does
not follow the stage order. Each has its own entry and exit criteria; none of
them may bypass a stage gate.

## Sync: refresh a change against the living spec

Use when the living spec changed (another change was archived) while this
change is still active.

Entry criteria:

- This change is at `specified` or later and not yet archived.
- The living spec has commits newer than this change's last sync.

Steps:

1. Diff the living spec since the last sync and list requirements touched by
   both sides.
2. For each overlap, rewrite this change's requirement against the new
   baseline and keep `Change: modify` with an updated `Previously:` line.
3. Re-run Plan for tasks that relied on the old wording; clear the boxes of tasks whose
   evidence no longer proves the new statement.
4. Record the sync date and baseline revision in `proposal.md` under
   **History**.

Exit criteria: the checker passes and no requirement contradicts the current
living spec.

## Update: change scope or requirements mid-flight

Use when implementation or review shows the accepted scope or a requirement is
wrong.

Entry criteria: a concrete reason with evidence (a failing scenario, a new
constraint, an owner decision).

Steps:

1. Add a dated entry under **History** in `proposal.md`: what changed, why,
   who decided.
2. Move status back to the earliest affected stage: `proposed` for scope
   changes, `specified` for requirement changes. Never move forward through an
   update.
3. Edit the affected files, then re-run every gate from that stage onward.
   Ticked tasks stay ticked only if their evidence still proves the edited
   requirement.

Exit criteria: owner acceptance of the new scope is recorded and the checker
passes at the restored status.

## Continue: resume an interrupted change

Use when picking up a change after a pause, a hand-off or a lost session.

Steps:

1. Read `proposal.md` status and **History**, then `tasks.md`.
2. Run the checker. Treat every finding as the first work item.
3. For the last ticked task, re-run its evidence command. If it fails, clear
   its box; stale evidence is not progress.
4. Re-read open questions in `notes/` and confirm they are still answered.
5. Continue the stage indicated by the status, starting at its entry criteria.

Exit criteria: the resumed stage's entry criteria hold and the next task is
identified.

## Bulk archive: archive several verified changes together

Use at release time when several verified changes touch overlapping
capabilities.

Steps:

1. List candidate folders and run the checker on all of them in one command:
   `python assets/check_spec_change.py <changes>/a <changes>/b --trace`.
   Exclude any folder with findings or a status other than `verified`.
2. Sort the remaining changes by merge date. Archive them in that order so
   later modifications apply on top of earlier ones.
3. Before each merge, check whether an earlier change in the batch touched the
   same requirement; if so, reconcile as described in
   [archive](stage-archive.md#conflict-handling).
4. After the batch, read each affected living spec once in full and run the
   checker on every archived folder.
5. Record the batch (release identifier and folder list) in the release notes.

Exit criteria: every candidate is either archived and passing or explicitly
left active with the reason.

## Close without archiving

Abandoned or superseded changes are not archived as delivered. Set
`Status: draft`, add a **History** entry with the reason and the superseding
change if any, and move the folder to `<changes-root>/closed/`. The living
spec is not touched.

## Sources

- [Git diff documentation](https://git-scm.com/docs/git-diff)
- [Semantic Versioning 2.0.0](https://semver.org/)
