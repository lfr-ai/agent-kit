# SQL persistence review guide

Reviewed 2026-10-23. Topic detail lives in the sibling references linked from
[SKILL.md](../SKILL.md).

## Decision table

| Question | Default | Deviate when |
| --- | --- | --- |
| ORM or Core? | ORM for aggregates with identity and relationships | Reports, bulk maintenance, and read models use Core `select` of columns |
| Sync or async? | Match the application's I/O model; async for an `asyncio` web stack | A CLI or batch job has no event loop: use the sync API |
| Repository per? | Aggregate root | Read models get a query service, not a repository |
| Who commits? | The unit of work, called by the use case | Never the repository or the route |
| Pagination? | Keyset | Small admin lists that need page numbers |
| Test engine? | SQLite for mapping, production engine for the contract suite | The adapter uses dialect features: production engine only |

## Review checklist

| Area | Question | Reference |
| --- | --- | --- |
| Mapping | Do port methods return domain objects only? | [ORM mapping](orm-mapping.md) |
| Types | Are columns `Mapped[...]` with explicit nullability, lengths, and aware timestamps? | [ORM mapping](orm-mapping.md) |
| Sessions | Is every session opened by a context manager and owned by one unit of work? | [sessions and transactions](sessions-transactions.md) |
| Transactions | Is there exactly one commit per use case, with no remote call inside? | [sessions and transactions](sessions-transactions.md) |
| SQL safety | Are all values bound and identifiers allow-listed? | [queries and loading](queries-loading.md) |
| Loading | Are relationships `lazy="raise"` and loaded explicitly? | [queries and loading](queries-loading.md) |
| Paging | Is every list ordered by a unique key and bounded? | [queries and loading](queries-loading.md) |
| Dialect | Are timeouts, pragmas, and locks configured for the engine in use? | [dialect specifics](dialects.md) |
| Tests | Does the contract suite run on the production engine? | [testing](testing.md) |

## Anti-patterns

- Domain entities that inherit from `DeclarativeBase`.
- `session.commit()` inside a repository method or after every statement.
- Module-level `session = Session()` or a global scoped session shared by tasks.
- `text(f"... {value} ...")`, `"... " + value`, `"... %s" % value`, or
  `"...{}".format(value)` as SQL text.
- Catching `Exception` around a query and returning an empty list.
- Loading a full table to filter or count in Python.
- `expire_on_commit=True` with async sessions, followed by attribute access.
- Swapping SQLite for PostgreSQL in tests and calling the adapter verified.

## Verification

1. `python assets/check_sql_safety.py src` reports no findings, or each
   remaining line carries `# sql-safety: reviewed` with a reason nearby.
2. The repository contract tests pass on the in-memory fake, SQLite, and the
   production engine.
3. A query-count test covers each list operation.
4. The type checker accepts the models and adapters without `Any` or casts.
5. Schema changes have a migration reviewed through the migrations skill.

## Limits

The checker is static: it cannot see SQL assembled in another module, values
already escaped by a trusted builder, or runtime pool exhaustion. Query plans,
lock waits, and pool sizing need measurement on a production-sized dataset.

## Primary sources

- [SQLAlchemy 2.0 documentation](https://docs.sqlalchemy.org/en/20/)
- [SQLAlchemy ORM session FAQ](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#session-frequently-asked-questions)
- [PEP 249: Python Database API Specification v2.0](https://peps.python.org/pep-0249/)
- [OWASP query parameterization cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/Query_Parameterization_Cheat_Sheet.html)
