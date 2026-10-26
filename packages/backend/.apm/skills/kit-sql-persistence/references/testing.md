# Testing persistence adapters

Reviewed 2026-10-23.

## Test layers

| Layer | Engine | Proves | Template |
| --- | --- | --- | --- |
| Domain and use cases | In-memory fake repository | Business rules without a database | `kit-domain-model` skill fakes |
| Adapter mapping | SQLite in-memory (`StaticPool`) | Row and domain mapping, eager loading, error translation | [conftest](../assets/conftest.py.template), [repository tests](../assets/test_repository.py.template) |
| Adapter contract on production engine | PostgreSQL in a disposable container | Constraints, locking, `JSONB`, dialect SQL, timeouts | Same tests with the `postgres` parameter |
| Migrations | Production engine | Upgrade, stairway, drift | `kit-database-migrations` skill |
| Static safety | None | No formatted SQL, sessions closed | [check_sql_safety.py](../assets/check_sql_safety.py) |

Run the same contract tests against the in-memory fake and the SQL adapter so
the fake cannot drift from real behavior.

## Rollback fixtures

Give each test a session bound to an outer connection transaction that is
rolled back afterwards. With `join_transaction_mode="create_savepoint"`, code
under test may call `commit()` without ending the outer transaction:

```python
async with engine.connect() as connection:
    outer = await connection.begin()
    factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    async with factory() as session:
        yield session
    await outer.rollback()
```

This keeps tests isolated and fast. It does not exercise two concurrent
transactions; write explicit concurrency tests with two independent sessions
on the production engine for optimistic and pessimistic locking.

## Testcontainers PostgreSQL

- Start one container per test session (`scope="session"`), pin the image by
  digest, and create the schema once (`run_sync(Base.metadata.create_all)` or the
  real migrations).
- Skip, do not fail, when Docker is unavailable on a developer machine; CI must
  run the tier.
- Never point tests at a shared database through an environment variable
  default.

## What to assert

- Round trip: `add` then `get` returns an equal domain object, including nested
  values, decimals, and timezone-aware timestamps.
- Every documented error: duplicate key, not found, stale version.
- Pagination: pages do not overlap, cover all rows, and are stable when rows are
  inserted between page requests.
- Query count for list operations stays constant as data grows.
- Commit discipline: leaving the unit of work without `commit()` persists
  nothing.

## Primary sources

- [Joining a session into an external transaction](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)
- [Testcontainers for Python](https://testcontainers-python.readthedocs.io/en/latest/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/en/latest/)
- [pytest fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)
