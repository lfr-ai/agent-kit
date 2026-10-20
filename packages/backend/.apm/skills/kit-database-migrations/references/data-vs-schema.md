# Data migrations versus schema migrations

## Keep them separate

A schema migration changes structure (tables, columns, constraints, indexes). A
data migration changes rows. Mixing both in one revision couples a fast,
transactional DDL step with a slow, volume-dependent update and makes rollback
and retry harder.

| Aspect | Schema migration | Data migration (backfill) |
| --- | --- | --- |
| Runs | In the deploy pipeline, before or after a release | As a revision or as a separate job |
| Duration | Seconds; bounded by locks | Proportional to rows |
| Transaction | One transaction (where supported) | Many small transactions |
| Retry | Re-run the revision | Resume from a checkpoint |
| Review focus | Locks and compatibility | Correctness, batching, concurrent writers |

## Where a backfill should live

- **Small tables** (thousands of rows, measured): a data step inside a dedicated
  revision is fine. Use `sa.table()` constructs, not application models.
- **Large tables**: run the backfill as an idempotent job (management command,
  worker task) that the expand revision enables and the contract revision
  depends on. Record completion (a marker row, a metric, or a verification
  query) so the contract migration can assert that it ran.

## Writing a safe backfill

1. Select work by primary key range or keyset pagination, never with a single
   `UPDATE ... WHERE new_col IS NULL` over the whole table.
2. Commit each batch. Keep batches small enough that each transaction holds row
   locks for well under a second at production volume.
3. Make each batch idempotent: only touch rows that still need the change
   (`WHERE customer_note IS NULL`), so reruns are safe.
4. Do not overwrite newer data. Running application code may already write the
   new column; the backfill must not clobber those values.
5. Throttle between batches when replicas or the write-ahead log fall behind.
6. Log progress as counts and the last processed key, never row contents.
7. Verify at the end with a query that proves no rows remain unconverted.

```python
orders = sa.table(
    "orders",
    sa.column("id", sa.BigInteger),
    sa.column("note", sa.Text),
    sa.column("customer_note", sa.Text),
)


def backfill(connection: sa.Connection, *, batch_size: int = 1000) -> int:
    last_id = 0
    updated = 0
    while True:
        ids = (
            connection.execute(
                sa.select(orders.c.id)
                .where(orders.c.id > last_id, orders.c.customer_note.is_(None))
                .order_by(orders.c.id)
                .limit(batch_size)
            )
            .scalars()
            .all()
        )
        if not ids:
            return updated
        result = connection.execute(
            orders.update()
            .where(orders.c.id.in_(ids), orders.c.customer_note.is_(None))
            .values(customer_note=orders.c.note)
        )
        connection.commit()
        updated += result.rowcount
        last_id = ids[-1]
```

## Conversions and semantics

- Write the mapping for every source value, including nulls, empty strings,
  out-of-range numbers, and invalid legacy data. Decide whether invalid data is
  migrated to null, to a sentinel, or reported and left for manual repair.
- Test conversions with representative edge values, not only an empty database.
- Time zones, collations, and numeric precision changes are data migrations even
  when the DDL looks trivial.

## Data fixes are migrations too

One-off corrections ("set status for orders created during the incident") belong
in version-controlled, reviewed scripts with a dry-run mode and a count check,
not in ad-hoc consoles. Keep personal or sensitive data out of the script and
its logs.

## Sources

- <https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.execute>
- <https://docs.sqlalchemy.org/en/20/core/dml.html>
- <https://www.postgresql.org/docs/current/sql-update.html>
- <https://www.postgresql.org/docs/current/queries-limit.html>
