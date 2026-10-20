# Database migrations guide

## Purpose

Plan, write, review, and test schema and data migrations that keep the service
available during rolling deploys and that can be recovered when something goes
wrong.

## Map of this skill

| Topic | Reference or asset |
| --- | --- |
| Compatible multi-step changes | [expand and contract](expand-contract.md) |
| Revision structure, heads, autogenerate | [Alembic hygiene](alembic-hygiene.md) |
| Backfills and conversions | [data versus schema](data-vs-schema.md) |
| Lock levels, timeouts, concurrent indexes | [locks](locking.md) |
| Rollback modes and roll forward | [rollback](rollback.md) |
| Test layers and rehearsal | [testing](testing.md) |
| Revision starting point | [revision template](../assets/alembic_revision.py.template) |
| Pytest suite | [migration tests](../assets/test_migrations.py.template) |
| Review record | [checklist](../assets/migration-checklist.md.template) |
| Raw SQL header | [SQL header](../assets/migration_header.template.sql) |
| Static scan | [safety checker](../assets/check_migration_safety.py) |

## Acceptance gates

- A written plan lists DDL steps, backfills, release order, expected duration,
  and the point of no return.
- Backfills are idempotent or resumable and report progress.
- Lock and load implications are reviewed for the target engine version, with
  mitigations such as timeouts and concurrent index builds.
- Tests cover upgrade, stairway, drift, and data conversion on the production
  engine.

## Failure modes

- Long-running table rewrites (type changes, volatile defaults) blocking traffic.
- A cheap `ALTER TABLE` queued behind a long query, stalling every later query.
- Backfills that overwrite newer user data written by already-deployed code.
- Missing indexes causing scans and timeouts in backfill or new queries.
- Transaction size limits, write-ahead log growth, or replica lag from one huge
  update.
- Concurrent index builds leaving an `INVALID` index after a failure.
- Multiple heads after parallel branches, causing a deploy to apply only one.

## Negative cases to exercise

- Interrupt a backfill mid-run and verify that it resumes without duplicates.
- Run old-version writes during the migration rehearsal and verify both versions
  keep working.
- Insert invalid legacy values and verify the documented conversion.
- Run a downgrade only where the rollback mode says it is supported; verify that
  forward-only revisions refuse with a clear message.

## Recovery and mitigation

- Prefer roll forward: a new corrective revision through the normal pipeline.
- Keep operator-run compensating scripts with dry-run output and row counts.
- For long-running batches, alert on stalled progress and support pause/resume.
- When rollback is unsafe, keep a compatibility path in the application until
  the corrective change ships, and write a short post-incident note.

## Scope and limits

The static checker is a conservative heuristic over Alembic operation calls. It
does not evaluate SQL built at runtime, engine-specific online DDL options, or
real lock timing. Staged rollouts, monitoring, and operator coordination remain
required.

## Sources

- <https://alembic.sqlalchemy.org/en/latest/>
- <https://martinfowler.com/articles/evodb.html>
- <https://www.postgresql.org/docs/current/explicit-locking.html>
