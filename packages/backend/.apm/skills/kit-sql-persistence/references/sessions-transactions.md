# Engines, sessions, and transaction boundaries

Reviewed 2026-10-23 against the SQLAlchemy 2.0 session and asyncio guides.

## Object lifetimes

| Object | Lifetime | Owner |
| --- | --- | --- |
| `Engine` / `AsyncEngine` (holds the pool) | Process | Composition root; `dispose()` at shutdown |
| `sessionmaker` / `async_sessionmaker` | Process | Composition root, injected into units of work |
| `Session` / `AsyncSession` | One request, job, or message | Unit of work, opened with `with` / `async with` |
| Transaction | One use case | Unit of work: `commit()` explicitly, roll back on any other exit |

Rules:

- Never share a session across threads, tasks, or requests. An `AsyncSession`
  is not safe for concurrent tasks; `asyncio.gather` over one session corrupts
  its state.
- Never create an engine per request; it defeats pooling and leaks connections.
- Open sessions only through a context manager (or a dependency that yields from
  one) so they always close; the bundled
  [checker](../assets/check_sql_safety.py) flags other session constructions.
- Async sessions: create the factory with `expire_on_commit=False`. Otherwise
  reading an attribute after `commit()` triggers an implicit refresh, which async
  code cannot perform (`MissingGreenlet`).
- Use async drivers with async engines: `postgresql+asyncpg://` or
  `postgresql+psycopg://` for PostgreSQL, `sqlite+aiosqlite://` for SQLite.
  Never call a synchronous driver from the event loop.

## Unit of work

The session already implements the unit-of-work pattern (identity map plus
change tracking). Wrap it behind the domain's `UnitOfWork` port so use cases do
not import SQLAlchemy:

```python
async with uow:
    order = await uow.orders.get(order_id)
    order.confirm(clock.now())
    await uow.orders.save(order)
    await uow.commit()
```

- Leaving the block without `commit()` rolls back. A forgotten commit is then a
  failing test, not a silent partial write.
- Repositories call `flush()` when they need database-generated values or want
  constraint errors raised inside the adapter; they never `commit()`.
- One unit of work per use case. Do not nest units of work; use
  `session.begin_nested()` (a savepoint) only for a deliberately retryable
  sub-step.
- Keep the transaction short: no remote calls, sleeps, or user interaction
  inside it. Write an outbox row instead of calling a broker before commit.

## Isolation and concurrency

| Need | Mechanism |
| --- | --- |
| Default read-modify-write on one row | `version_id_col` optimistic check; retry the whole use case on conflict |
| Serialize work on one hot row | `select(...).with_for_update()` inside the unit of work (PostgreSQL; ignored by SQLite) |
| Skip rows another worker holds (job queues) | `with_for_update(skip_locked=True)` |
| Cross-row invariant without a constraint | `isolation_level="SERIALIZABLE"` for that unit of work, and retry on serialization failure (SQLSTATE `40001`) |
| Single-run job or migration guard | PostgreSQL advisory lock; see [dialect specifics](dialects.md) |

Set isolation per engine with `create_engine(..., isolation_level=...)` or per
connection with `connection.execution_options(isolation_level=...)`. Retries
re-run the whole unit of work, so the use case must be idempotent.

## Pool sizing and timeouts

- Size the pool from the database's connection limit divided by the number of
  application processes, minus headroom for migrations and operators. A larger
  pool than the database can serve only moves the queue.
- Set `pool_timeout` (seconds to wait for a connection) low enough to fail fast,
  `pool_pre_ping=True` to discard dead connections, and `pool_recycle` below any
  proxy or server idle timeout.
- Behind an external connection-pooling proxy in transaction mode, use
  `NullPool` in the application and disable server-side prepared statement
  caching as the driver documents.
- Set server-side `statement_timeout`, `lock_timeout`, and
  `idle_in_transaction_session_timeout`; client-side timeouts alone leave work
  running on the server. The [session factory](../assets/session_factory.py.template)
  shows connection settings for asyncpg and SQLite.

## Failure modes

- Lazy load in async code raises `MissingGreenlet`; fix by eager loading, not by
  wrapping the call in `run_sync`.
- Connection leak: a session created without a context manager under an
  exception path; the pool reaches `pool_size + max_overflow` and requests time
  out.
- Long transaction holding locks while waiting for an HTTP call.
- Retried non-idempotent use case after a commit whose acknowledgement was lost.

## Primary sources

- [Session basics](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
- [Managing transactions](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)
- [Asynchronous I/O (asyncio)](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Connection pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html)
- [Setting transaction isolation levels](https://docs.sqlalchemy.org/en/20/core/connections.html#setting-transaction-isolation-levels-including-dbapi-autocommit)
- [PostgreSQL client connection defaults](https://www.postgresql.org/docs/current/runtime-config-client.html)
- [PostgreSQL transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html)
