---
description: Author a reviewable schema or data migration with expand-contract phasing, safe locking, honest rollback, safety checks, and migration tests.
argument-hint: The schema or data change, e.g. "add a non-null status to orders"
agent: agent
---

# Add a database migration

Write a migration that every running application version tolerates and that an
operator can roll out and, where possible, roll back. Never run it against a
live or shared database from this session.

## Input

- The user-supplied argument describes the schema or data change. Ask for the
  database engine and version if the repository does not declare them.

## Procedure

1. Load [kit-database-migrations](../skills/kit-database-migrations/SKILL.md)
   and follow its procedure and commands.
2. Read the migration tool configuration, the current head, naming
   conventions, and how deployment orders migrations relative to releases.
3. List every concurrent reader and writer: application versions, workers,
   scheduled jobs, reports, replicas.
4. Choose the phase plan. If old and new code overlap, split into expand,
   compatible code release, backfill, switch, and contract revisions.
5. Write one logical change per revision. Record the phase, release
   dependency, rollback mode, and point of no return in the revision docstring.
6. Keep schema and data changes in separate revisions. Make backfills batched,
   idempotent, and resumable.
7. Review lock level, table rewrite risk, and duration for each statement; set
   lock and statement timeouts; build large indexes without blocking writes
   where the engine supports it.
8. Define nullability, defaults, constraints, and how nulls, empty values, and
   invalid legacy rows convert.
9. Implement the downgrade honestly or mark the revision forward-only with the
   recovery path.
10. Run the skill's migration safety checker on the revisions; restructure or
    waive each finding with a written reason.
11. Add tests: single head, upgrade from empty, stairway up and down, model
    drift, and data conversion with representative rows.
12. Generate the offline SQL for review and run the migration tests.

## Acceptance gates

- [ ] Exactly one head; each revision documents phase and rollback mode.
- [ ] The safety checker reports no finding without a written waiver.
- [ ] All running versions stay compatible during rollout.
- [ ] No command touched a live or shared environment.

## Output

The phase plan as a table (revision, phase, rollback mode, release
dependency), the generated SQL summary, checker and test results, and the
operator rollout notes including the point of no return.
