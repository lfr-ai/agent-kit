---
name: kit-sql-persistence
description: Use when implementing a SQLAlchemy 2 repository, unit of work, session, query or PostgreSQL/SQLite adapter.
license: MIT
---

# Persist domain objects through SQLAlchemy

## Procedure

1. Read the domain port the adapter implements, the supported engines and
   versions, the driver (sync or async), and existing persistence conventions.
   Schema changes go through the `kit-database-migrations` skill; port design
   belongs to the `kit-domain-model` skill.
2. Map tables with typed `DeclarativeBase` models (`Mapped[...]`,
   `mapped_column`), a constraint naming convention, aware UTC timestamps, and
   `lazy="raise"` relationships per [ORM mapping](references/orm-mapping.md);
   start from the [models template](assets/models_base.py.template).
3. Write the repository adapter from the
   [repository template](assets/repository.py.template) against the
   [repository port](assets/order_ports.py.template) and the minimal
   [order types](assets/orders.py.template) (replace them with the project's own
   domain model): explicit row-to-domain mapping functions, eager loading,
   translated driver errors, and no `commit()`. Rows never leave the adapter.
4. Own the transaction in a [unit of work](assets/unit_of_work.py.template):
   one session per use case opened by `async with`, explicit `commit()`,
   rollback on every other exit, per
   [sessions and transactions](references/sessions-transactions.md).
5. Build the engine and session factory once in the composition root from the
   [session factory template](assets/session_factory.py.template): async driver,
   pool limits, `pool_pre_ping`, server-side statement and lock timeouts, SQLite
   pragmas, and `expire_on_commit=False`.
6. Write queries per [queries and loading](references/queries-loading.md):
   bound parameters only, allow-listed identifiers, `selectinload` or
   `joinedload` instead of N+1, keyset pagination ordered by a unique key, and
   set-based bulk statements.
7. Apply engine-specific rules (`JSONB`, indexes, advisory locks,
   `statement_timeout`; WAL, `foreign_keys`, `busy_timeout`, one writer) from
   [dialect specifics](references/dialects.md).
8. Adapt the [fixtures](assets/conftest.py.template) and
   [contract tests](assets/test_repository.py.template) per
   [testing](references/testing.md): rollback-isolated sessions, SQLite for fast
   mapping checks, and a disposable PostgreSQL container for the release gate.
9. Run [check_sql_safety.py](assets/check_sql_safety.py) on the touched paths
   and resolve or explicitly waive every finding.
10. Review the change against the [persistence guide](references/guide.md)
    checklist, anti-patterns, and limits.

## Acceptance gates

- Port methods return domain objects; no ORM row, session, or SQLAlchemy type
  crosses into domain or application code.
- Each use case commits at most once, through its unit of work; repositories
  never commit, and sessions are always opened by a context manager.
- No SQL text is built with f-strings, concatenation, `%`, or `str.format`;
  identifiers come from an allow-list.
- Every list query is bounded, ordered by a unique key, and loads relations
  explicitly; a query-count test covers it.
- Engine configuration sets pool limits, pre-ping, and server-side timeouts
  (PostgreSQL) or the foreign-key, WAL, and busy-timeout pragmas (SQLite).
- The repository contract tests pass on the production engine, not only SQLite.
- `check_sql_safety.py` reports no unreviewed findings.

## Checker

```text
python check_sql_safety.py src
python check_sql_safety.py src tests --templates --exclude migrations
```

Prints `path:line: rule: message`; exit 0 clean, 1 findings, 2 unusable input.
A reviewed line may carry `# sql-safety: reviewed`. The checker traces only
simple assignments in one scope; it does not prove a query is safe or fast.

## References

- [Persistence review guide](references/guide.md)
- [ORM mapping and repository adapters](references/orm-mapping.md)
- [Sessions and transactions](references/sessions-transactions.md)
- [Queries, loading, pagination, and bulk work](references/queries-loading.md)
- [PostgreSQL and SQLite specifics](references/dialects.md)
- [Testing persistence adapters](references/testing.md)
