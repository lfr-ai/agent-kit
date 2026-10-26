# PostgreSQL and SQLite specifics

Reviewed 2026-10-23 against the PostgreSQL current manual, the SQLite
documentation, and the SQLAlchemy dialect pages.

## PostgreSQL

| Topic | Guidance |
| --- | --- |
| Drivers | `asyncpg` (`postgresql+asyncpg`) or psycopg 3 (`postgresql+psycopg`, sync and async). Pin the driver with SQLAlchemy |
| `JSONB` | Use `sqlalchemy.dialects.postgresql.JSONB` for semi-structured attributes queried by key; index with `GIN` (`jsonb_path_ops` for containment only). Keep fields that have invariants or joins in real columns |
| Indexes | Index every foreign key used in joins or loaders; use composite indexes in the order of equality then range predicates; partial indexes (`postgresql_where=`) for hot subsets; build large ones `CONCURRENTLY` through a migration |
| Timeouts | Set `statement_timeout`, `lock_timeout`, and `idle_in_transaction_session_timeout` per role or per connection (`server_settings` for asyncpg, `options="-c ..."` for psycopg) |
| Row locks | `with_for_update()`, `skip_locked=True` for work queues, `nowait=True` to fail fast |
| Advisory locks | `SELECT pg_try_advisory_xact_lock(:key)` inside the transaction for a single-runner job; the lock is released at commit or rollback. Derive the key from a stable constant, never from user input without hashing |
| Upserts | `insert(...).on_conflict_do_update(...)` with an explicit conflict target |
| Generated values | Prefer application-generated UUIDs (time-ordered UUIDv7 keeps index locality) or identity columns; use `RETURNING` instead of a second query |
| Isolation | Default `READ COMMITTED`; `SERIALIZABLE` requires a retry loop on SQLSTATE `40001` |

## SQLite

| Topic | Guidance |
| --- | --- |
| Drivers | Stdlib `sqlite3` (sync) or `aiosqlite` (`sqlite+aiosqlite`) |
| Foreign keys | Off by default per connection: run `PRAGMA foreign_keys = ON` in a `connect` event listener |
| Concurrency | One writer at a time. `PRAGMA journal_mode = WAL` lets readers proceed during a write; keep write transactions short |
| Lock waits | `PRAGMA busy_timeout = <ms>` (or the driver `timeout`) so a second writer waits instead of failing with `database is locked` |
| Durability | `PRAGMA synchronous = NORMAL` is the usual WAL pairing; `FULL` for maximum durability |
| Types | Dynamic typing: enforce types with `STRICT` tables or check constraints; store decimals as text or integer minor units |
| In-memory databases | Each connection gets its own database; tests use `StaticPool` with one shared connection |
| Unsupported | `SELECT ... FOR UPDATE`, advisory locks, many `ALTER TABLE` forms (migrations use batch mode) |

The [session factory template](../assets/session_factory.py.template) installs
the SQLite pragmas on every new connection through
`event.listen(engine.sync_engine, "connect", ...)`.

## Choosing the engine for tests

SQLite in-memory is fast and good for adapter mapping logic, but it accepts
statements PostgreSQL rejects and lacks row locks, `JSONB`, and the same
constraint timing. Run the repository contract suite against the production
engine before release; see [testing](testing.md).

## Primary sources

- [SQLAlchemy PostgreSQL dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)
- [SQLAlchemy SQLite dialect](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html)
- [PostgreSQL JSON types](https://www.postgresql.org/docs/current/datatype-json.html)
- [PostgreSQL index types](https://www.postgresql.org/docs/current/indexes-types.html)
- [PostgreSQL advisory lock functions](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS)
- [PostgreSQL client connection defaults](https://www.postgresql.org/docs/current/runtime-config-client.html)
- [SQLite PRAGMA statements](https://www.sqlite.org/pragma.html)
- [SQLite write-ahead logging](https://www.sqlite.org/wal.html)
- [SQLite STRICT tables](https://www.sqlite.org/stricttables.html)
- [asyncpg connection API](https://magicstack.github.io/asyncpg/current/api/index.html)
