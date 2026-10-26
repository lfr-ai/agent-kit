# Queries, loading, pagination, and bulk work

Reviewed 2026-10-23 against the SQLAlchemy 2.0 ORM querying guide.

## Parameterized SQL only

Every value reaches the database as a bound parameter. Build statements with
the expression language (`select`, `insert`, `update`) or with `text()` plus
named parameters:

```python
# Good: values are bound; the driver never parses them as SQL.
statement = text("SELECT id FROM orders WHERE customer_id = :customer_id")
rows = await session.execute(statement, {"customer_id": customer_id})

# Good: typed binds when the driver needs them.
statement = text("SELECT id FROM orders WHERE created_at >= :since").bindparams(
    bindparam("since", type_=DateTime(timezone=True))
)

# Bad: f-string, concatenation, %-formatting, or str.format build SQL text.
await session.execute(
    text(f"SELECT id FROM orders WHERE customer_id = '{customer_id}'")
)
```

Identifiers (table, column, sort direction) cannot be bound. Map user input to
a closed allow-list and use the mapped column object:

```python
_SORT_COLUMNS = {"created": OrderRow.created_at, "total": OrderRow.total}
statement = select(OrderRow).order_by(_SORT_COLUMNS[sort_key].desc())
```

`IN` lists use `column.in_(values)` (or `bindparam(..., expanding=True)` with
`text()`), never a joined string. The
[checker](../assets/check_sql_safety.py) flags formatted SQL passed to
`execute`, `exec_driver_sql`, `scalar(s)`, `stream`, or `text`.

## Eager loading and N+1 avoidance

| Shape | Loader | Notes |
| --- | --- | --- |
| Collection (one-to-many, many-to-many) | `selectinload(Parent.children)` | One extra `SELECT ... WHERE parent_id IN (...)`; no row multiplication |
| Many-to-one or one-to-one | `joinedload(Child.parent)` | One `LEFT OUTER JOIN`; with a joined collection call `.unique()` on the result |
| Column subset for read models | `select(OrderRow.id, OrderRow.status)` or `load_only(...)` | Do not hydrate ORM objects for a report |
| Prevent accidental loads | `relationship(lazy="raise")` or `raiseload("*")` | Turns N+1 into a test failure |

Measure the query count in tests (an engine `before_cursor_execute` listener
counting statements) for list endpoints, so N+1 regressions fail.

## Pagination

| Method | Use when | Cost |
| --- | --- | --- |
| Keyset (seek): `WHERE (created_at, id) > (:created_at, :id) ORDER BY created_at, id LIMIT :n` | Large or changing tables, infinite scroll, exports | Constant per page; needs an index on the sort key; no random page jumps |
| Offset: `ORDER BY id LIMIT :n OFFSET :k` | Small, stable admin lists with page numbers | Grows with `k`; rows shift when data changes |

Always order by a unique key (append the primary key as a tie-breaker). Fetch
`limit + 1` rows to know whether a next page exists. Encode the last key as an
opaque cursor at the transport boundary; the API side is covered by the
`kit-api-contracts` skill.

## Bulk operations

- Insert many rows with one statement:
  `await session.execute(insert(OrderRow), [{"id": ..., ...}, ...])`. The ORM
  batches this as an executemany or a multi-row `INSERT` with `RETURNING` where
  the dialect supports it.
- Upsert with the dialect construct:
  `postgresql.insert(Row).on_conflict_do_update(index_elements=[...], set_=...)`
  or `sqlite.insert(Row).on_conflict_do_nothing()`.
- Bulk `update(Row).where(...).values(...)` and `delete(Row).where(...)` bypass
  per-object events and version checks; use them for set-based maintenance, not
  for aggregate changes that must enforce domain invariants.
- Process large result sets with `await session.stream_scalars(...)` or
  `yield_per`, and batch writes (for example 1000 rows per transaction) so a
  failure does not roll back hours of work.

## Failure modes

- `DISTINCT` or `GROUP BY` added to hide duplicated rows from a joined collection.
- `OFFSET` deep paging that scans and discards millions of rows.
- Foreign keys without an index used in `selectinload` or `WHERE`.
- `session.add_all` of 100 000 ORM objects in one flush exhausting memory.

## Primary sources

- [ORM querying guide](https://docs.sqlalchemy.org/en/20/orm/queryguide/index.html)
- [Sending parameters with text()](https://docs.sqlalchemy.org/en/20/tutorial/dbapi_transactions.html#sending-parameters)
- [text() and bindparams](https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.text)
- [Relationship loading techniques](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html)
- [ORM bulk INSERT, UPDATE, and DELETE](https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html)
- [OWASP SQL injection prevention cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
- [PostgreSQL row constructor comparison](https://www.postgresql.org/docs/current/functions-comparisons.html#ROW-WISE-COMPARISON)
