# Alembic revision hygiene

## One linear history

- Every revision has a unique `revision` id and a `down_revision` pointing at its
  parent. `alembic heads` must show exactly one head on the main branch.
- When two branches each add a revision, resolve with `alembic merge heads -m
  "merge ..."` before merging the second branch, or rebase the later revision
  onto the new head by editing its `down_revision`. CI should fail when more
  than one head exists.
- Never edit a revision that has run in any shared environment. Fix forward with
  a new revision.
- Do not delete old revisions to "clean up" unless every environment is past
  them and you deliberately squash into a new baseline with a documented
  procedure.

## Revision content

- One logical change per revision, with a message that describes intent
  (`add customer_note to orders`), not the tool (`autogenerate`).
- Put the phase (expand, backfill, contract) and the release dependency in the
  module docstring. The [revision template](../assets/alembic_revision.py.template)
  has fields for both.
- Import only what the migration needs: `alembic.op`, `sqlalchemy as sa`, and
  dialect types. Do not import application models; they change after the
  migration is written and the migration must keep producing the same schema
  forever. Declare lightweight `sa.table()` / `sa.column()` constructs for data
  steps instead.
- Name constraints and indexes explicitly (or configure a naming convention on
  `MetaData`) so later migrations can drop them by name on every backend.
- Keep `downgrade()` honest. Either implement a true reverse of a reversible
  step, or raise an error that explains why the step cannot be reversed. An
  empty `pass` that silently does nothing is worse than either.

## Autogenerate

- Treat autogenerate output as a draft. It cannot detect renames (it emits a drop
  and an add), it may miss server defaults or some type changes depending on
  configuration, and it does not order steps for zero-downtime deploys.
- Enable `compare_type` (default in recent releases) and consider
  `compare_server_default` when defaults matter.
- Run `alembic check` in CI to fail when the models and the latest revision
  disagree, so missing migrations are caught before review.

## Transactions

- On PostgreSQL, Alembic runs each migration inside a transaction by default, so
  DDL is atomic per run. Set `transaction_per_migration=True` in `env.py` when
  each revision should commit independently, which limits how long locks are
  held when several revisions run together.
- Statements that cannot run in a transaction (for example
  `CREATE INDEX CONCURRENTLY`, some `ALTER TYPE ... ADD VALUE` uses) go inside
  `with op.get_context().autocommit_block():`.
- MySQL and several other engines commit DDL implicitly; a failed revision can
  leave the schema half-applied. Keep those revisions very small.

## Batch mode for SQLite

SQLite cannot alter most column properties in place. `op.batch_alter_table()`
recreates the table and copies data. It is correct but takes a full copy; avoid
it on large tables and never assume it behaves like an online change on other
engines.

## Offline SQL

`alembic upgrade <rev> --sql` renders SQL without connecting. Use it to review
exact DDL, to hand scripts to a database administrator, or when the deploy
pipeline must apply SQL through another tool. Data migrations that read rows do
not work offline.

## Static review

Run [check_migration_safety.py](../assets/check_migration_safety.py) on the
`versions/` directory in CI. It flags drops, renames, type changes, NOT NULL
tightening, non-concurrent PostgreSQL index builds, and destructive raw SQL. A
reviewed exception carries `# migration-safety: reviewed` and a reason on the
operation line or the line above.

## Sources

- <https://alembic.sqlalchemy.org/en/latest/tutorial.html>
- <https://alembic.sqlalchemy.org/en/latest/branches.html>
- <https://alembic.sqlalchemy.org/en/latest/autogenerate.html>
- <https://alembic.sqlalchemy.org/en/latest/ops.html>
- <https://alembic.sqlalchemy.org/en/latest/api/runtime.html>
- <https://alembic.sqlalchemy.org/en/latest/batch.html>
- <https://alembic.sqlalchemy.org/en/latest/offline.html>
- <https://alembic.sqlalchemy.org/en/latest/naming.html>
