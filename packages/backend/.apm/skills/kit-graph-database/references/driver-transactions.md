# Driver lifecycle and transactions (Python)

Reviewed 2026-10-23 against the Neo4j Python Driver Manual and API docs for
driver 6 (current; driver 5 uses the same calls). Install the `neo4j` package;
the old `neo4j-driver` name is deprecated and receives no driver 6 updates.

## Object lifetimes

| Object | Lifetime | Rule |
| --- | --- | --- |
| `Driver` / `AsyncDriver` | Process | Create once in the composition root, call `verify_connectivity()` at startup, `close()` at shutdown. Thread-safe and holds the pool |
| Session | One unit of work | Cheap; open with `with` / `async with`; never share across threads or tasks |
| Managed transaction | One transaction function call | Created by `execute_read` / `execute_write`; retried on transient errors |
| Result | Inside the transaction function | Consume it there (`list(result)`, `result.single()`, `result.data()`); never return the `Result` object |

## Choosing the API

| Need | API |
| --- | --- |
| One query, default retries, simplest code | `driver.execute_query(query, routing_=RoutingControl.READ, database_=db, **params)` |
| Several queries or client logic in one atomic unit | `session.execute_write(work, ...)` / `session.execute_read(work, ...)` |
| `CALL { ... } IN TRANSACTIONS`, `LOAD CSV` batches | Auto-commit `session.run(...)` (not retried; make it resumable) |
| Explicit begin and commit across code paths | `session.begin_transaction()`; you own retries |

Always pass the database name (`database_=` or `driver.session(database=...)`):
it avoids an extra round trip to resolve the home database and makes the target
explicit. Route reads with `execute_read` or `RoutingControl.READ` so clusters
can serve them from secondaries.

## Retryable, idempotent units

The driver re-runs a managed transaction function when the failure is
transient (leader switch, deadlock, temporary unavailability) until
`max_transaction_retry_time` expires. Therefore the function must:

- run only database work: no HTTP calls, message publishing, or file writes;
- be idempotent: use `MERGE` on keys or guard writes with the current state;
- not depend on state mutated by a previous attempt (build inputs before the call);
- consume and return plain values, not records bound to the transaction.

Set a server-side timeout per transaction with `neo4j.unit_of_work(timeout=...)`
on the transaction function or `Query(text, timeout=...)` for `execute_query`.

## Async driver

`AsyncGraphDatabase.driver(...)` returns an `AsyncDriver`; transaction
functions take an `AsyncManagedTransaction` and are coroutines:

```python
async def _find(
    tx: AsyncManagedTransaction, customer_id: str
) -> list[dict[str, object]]:
    result = await tx.run(FIND_ORDERS, customer_id=customer_id, limit=PAGE_SIZE)
    return await result.data()


async with driver.session(database=database) as session:
    rows = await session.execute_read(_find, customer_id)
```

Do not mix the sync driver into an event loop. Bound concurrency with a
semaphore; each concurrent task needs its own session.

## Consistency

Sessions chain bookmarks automatically, so a read in the same session sees the
session's earlier writes. Across sessions, `execute_query` shares a bookmark
manager by default; for explicit sessions pass
`bookmark_manager=driver.execute_query_bookmark_manager` (or collect bookmarks)
when a later read must observe an earlier write on a cluster.

## Error translation

| Driver exception | Adapter behavior |
| --- | --- |
| `ConstraintError` (uniqueness violation) | Raise the port's duplicate error |
| `TransientError`, `ServiceUnavailable`, `SessionExpired` | Already retried by managed transactions; after that raise the port's unavailable error |
| `ClientError` with a syntax or semantic code | A defect: let it fail tests loudly |
| `AuthError` | Configuration error at startup |

Chain the cause (`raise ... from error`) and log once at the handling boundary
without query parameters that may contain personal data.

## Primary sources

- [Python Driver Manual: run your own transactions](https://neo4j.com/docs/python-manual/current/transactions/)
- [Python Driver Manual: query the database](https://neo4j.com/docs/python-manual/current/query-simple/)
- [Python Driver Manual: run concurrent transactions (async)](https://neo4j.com/docs/python-manual/current/concurrency/)
- [Python Driver Manual: performance recommendations](https://neo4j.com/docs/python-manual/current/performance/)
- [Python driver API reference](https://neo4j.com/docs/api/python-driver/current/api.html)
- [Python driver async API reference](https://neo4j.com/docs/api/python-driver/current/async_api.html)
