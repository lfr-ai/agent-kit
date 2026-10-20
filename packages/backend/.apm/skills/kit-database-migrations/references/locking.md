# Locks and long transactions

Most migration outages are not caused by slow DDL but by waiting for a lock.
On PostgreSQL, an `ALTER TABLE` that needs an `ACCESS EXCLUSIVE` lock queues
behind any long-running query on the table, and every new query then queues
behind the `ALTER`. A one-millisecond change can block traffic for minutes.

## PostgreSQL lock levels for common operations

| Operation | Lock taken | Notes |
| --- | --- | --- |
| `ADD COLUMN` nullable, or with a non-volatile default | `ACCESS EXCLUSIVE`, brief | No table rewrite on PostgreSQL 11+ |
| `ADD COLUMN` with a volatile default (`now()`, `random()`) | `ACCESS EXCLUSIVE` | Rewrites the table |
| `ALTER COLUMN TYPE` | `ACCESS EXCLUSIVE` | Usually rewrites the table and rebuilds indexes |
| `SET NOT NULL` | `ACCESS EXCLUSIVE` | Scans the table unless a validated `CHECK (col IS NOT NULL)` exists (PostgreSQL 12+) |
| `ADD CONSTRAINT ... NOT VALID` | Brief lock | Skips checking existing rows |
| `VALIDATE CONSTRAINT` | `SHARE UPDATE EXCLUSIVE` | Scans without blocking reads or writes |
| `ADD FOREIGN KEY` | `SHARE ROW EXCLUSIVE` on both tables | Use `NOT VALID`, then validate |
| `CREATE INDEX` | `SHARE` | Blocks writes for the whole build |
| `CREATE INDEX CONCURRENTLY` | `SHARE UPDATE EXCLUSIVE` | Slower, no write blocking; not allowed in a transaction block |
| `DROP TABLE`, `DROP COLUMN` | `ACCESS EXCLUSIVE`, brief | Destructive; see expand/contract |

Verify against the documentation for the exact server version in use; lock
behavior changes between major versions.

## Guard every migration with timeouts

Set a short `lock_timeout` so a migration that cannot get its lock fails fast
instead of queueing traffic behind it, and a `statement_timeout` as a ceiling:

```python
def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.execute("SET LOCAL statement_timeout = '60s'")
    op.add_column("orders", sa.Column("customer_note", sa.Text(), nullable=True))
```

`SET LOCAL` lasts until the end of the current transaction. When the lock
timeout fires, retry the deploy step later rather than raising the timeout.
Configure the values in `env.py` when every revision should share them.

## Concurrent index builds

```python
def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_orders_customer_id",
            "orders",
            ["customer_id"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )
```

- A failed concurrent build leaves an `INVALID` index. Drop it (concurrently)
  before retrying; `if_not_exists=True` alone would skip the broken index.
- Concurrent builds wait for existing transactions that could see the table; a
  forgotten idle-in-transaction session stalls them.

## Long transactions

- Never wrap a large backfill in the same transaction as the DDL; see
  [data versus schema](data-vs-schema.md).
- Long transactions hold back vacuum and can bloat tables and indexes. Commit in
  batches.
- Check for blockers before a risky step: long-running queries and
  idle-in-transaction sessions in `pg_stat_activity`.

## Other engines

- MySQL/InnoDB: many `ALTER TABLE` forms support `ALGORITHM=INPLACE` or
  `INSTANT`; specify the algorithm and lock level explicitly so the statement
  fails instead of silently copying the table.
- SQL Server: online index operations depend on edition; schema modification
  locks block all access.
- SQLite: a single writer; table rebuilds through batch mode copy the whole
  table.

## Sources

- <https://www.postgresql.org/docs/current/explicit-locking.html>
- <https://www.postgresql.org/docs/current/sql-altertable.html>
- <https://www.postgresql.org/docs/current/sql-createindex.html#SQL-CREATEINDEX-CONCURRENTLY>
- <https://www.postgresql.org/docs/current/runtime-config-client.html>
- <https://www.postgresql.org/docs/current/monitoring-stats.html>
- <https://alembic.sqlalchemy.org/en/latest/api/runtime.html>
- <https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html>
