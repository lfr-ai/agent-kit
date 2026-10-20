# Rollback strategy

## Decide before you deploy

For every revision, record one of three rollback modes in its docstring and in
the [checklist](../assets/migration-checklist.md.template):

| Mode | Meaning | Typical changes |
| --- | --- | --- |
| Reversible | `downgrade()` restores the previous schema without data loss | Adding a nullable column, table, or index |
| Forward-only | Recovery is a new corrective revision; `downgrade()` raises | Backfills, type changes, merges of data |
| Destructive | Data is removed; recovery requires a backup restore | Dropping columns or tables |

The release and the migration must roll back independently. With
expand/contract, rolling back the application never requires rolling back the
schema, because the expanded schema supports both versions.

## The point of no return

Every plan names the step after which a rollback is unsafe (usually "release N
stops writing the old column" or "contract migration runs"). Before that step:

- Confirm a recent, restorable backup or point-in-time recovery window.
- Confirm monitoring shows the new code path is healthy.
- Confirm no old-version workers or queued jobs remain.

## Implementing downgrade

- Reverse operations in the reverse order of `upgrade()`.
- A downgrade that drops a column added by the upgrade loses data written since;
  say so in the docstring.
- For forward-only revisions:

  ```python
  def downgrade() -> None:
      raise RuntimeError(
          "Forward-only: backfill cannot be reversed; deploy a corrective revision."
      )
  ```

- Never leave `downgrade()` as `pass` when `upgrade()` changed something.

## Roll forward

Most production incidents are resolved by rolling forward: a new revision that
fixes the schema or data, deployed through the normal pipeline. Prepare:

- A corrective revision template and the commands to generate and test it.
- Compensating data scripts with dry-run output and row-count checks.
- An operator runbook entry naming who approves a restore.

## Partial failure

- PostgreSQL: a failed revision inside a transaction leaves no change, except
  statements run in an autocommit block (for example a concurrent index build,
  which may leave an `INVALID` index).
- Engines with implicit DDL commits (MySQL): a revision with several DDL
  statements can stop halfway. Keep one DDL statement per revision there, and
  write each step to be re-runnable (`IF NOT EXISTS`, existence checks).
- Interrupted backfills resume from their last committed batch because each
  batch is idempotent.

## Sources

- <https://alembic.sqlalchemy.org/en/latest/tutorial.html#downgrading>
- <https://www.postgresql.org/docs/current/continuous-archiving.html>
- <https://martinfowler.com/bliki/ParallelChange.html>
