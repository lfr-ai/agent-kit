---
name: kit-database-migrations
description: Use when changing persisted schema or data with an ordered, reviewable migration and recovery plan.
license: MIT
---

# Evolve stored data safely

## Procedure

1. Read migration conventions, the current head (`alembic heads`), supported database engines and versions, and how deploys order migrations relative to application releases.
2. Identify every reader and writer that may run concurrently with the change: application versions, workers, scheduled jobs, reports, and replicas.
3. Plan the change as expand, deploy compatible code, backfill, switch, then contract whenever old and new versions overlap; see [expand and contract](references/expand-contract.md).
4. Write one logical change per revision from the [revision template](assets/alembic_revision.py.template). Record phase, release dependency, rollback mode, and point of no return in its docstring; see [Alembic hygiene](references/alembic-hygiene.md).
5. Keep schema and data changes in separate revisions. Make backfills batched, idempotent, resumable, and safe against concurrent writes; see [data versus schema](references/data-vs-schema.md).
6. Review the lock level, rewrite risk, and duration of every statement for the target engine version. Set `lock_timeout` and `statement_timeout`; build PostgreSQL indexes concurrently inside an autocommit block; see [locks and long transactions](references/locking.md).
7. Define nullability, defaults, constraints, indexes, and conversion semantics explicitly, including nulls, empty values, and invalid legacy data.
8. Choose the rollback mode (reversible, forward-only, destructive) and implement `downgrade()` honestly; see [rollback strategy](references/rollback.md).
9. Run [check_migration_safety.py](assets/check_migration_safety.py) on the revisions directory. Resolve each finding by restructuring, or waive it with `# migration-safety: reviewed` and a written reason.
10. Adapt the [migration tests](assets/test_migrations.py.template): single head, upgrade from empty, stairway, model drift, and data conversion with representative rows; see [testing migrations](references/testing.md).
11. Rehearse contract and data migrations on a production-sized, masked snapshot and record duration and lock waits.
12. Complete the [review checklist](assets/migration-checklist.md.template) and document the rollout order and the point after which rollback is unsafe.
13. For teams applying raw SQL files, start from the [SQL header](assets/migration_header.template.sql) instead of the Alembic template.
14. Never run a migration against a live or shared environment from an authoring session; deployment belongs to the operator pipeline.
15. Read the [migration guide](references/guide.md) for failure modes, negative cases, and recovery.

## Acceptance gates

- Exactly one head; every revision has a phase, rollback mode, and point of no return in its docstring.
- The static safety checker reports no unreviewed findings, and each waiver states why the operation is safe now.
- Every running application version is compatible with the schema before, during, and after the migration.
- Upgrade, stairway, drift, and data conversion tests pass on the production engine and major version.
- Backfills are batched, idempotent, and verified complete by a query before any contract step.
- Destructive steps have a confirmed backup or point-in-time recovery window and an operator-approved runbook entry.

## Commands

```text
alembic heads
alembic upgrade head --sql > review.sql
alembic check
python assets/check_migration_safety.py migrations/versions --dialect postgresql
python assets/check_migration_safety.py --self-test
pytest tests/integration/test_migrations.py -q
```

An empty-database upgrade alone does not prove a production-safe migration.
