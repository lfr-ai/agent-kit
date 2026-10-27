# Testing caches deterministically

Verified as of 2026-10-27 against the pytest and Python `asyncio`
documentation. Test-tier conventions follow the project's test strategy;
this reference covers what is specific to caches.

Caches fail in ways ordinary tests miss: values that never expire, keys that
collide across tenants, stampedes, stale reads after writes, and outages
that take the service down. Every one of these can be tested without
sleeping and without a network.

## Inject time, randomness, and waiting

Hard-coded `time.monotonic()`, `random.random()`, and `asyncio.sleep()` make
expiry, jitter, and lock polling untestable. The templates accept them as
constructor arguments:

| Dependency | Production | Test |
| --- | --- | --- |
| Clock | `time.monotonic` | A `FakeClock` with `advance(seconds)` |
| Jitter source | `random.uniform` | A lambda returning a fixed offset |
| Lock token | `secrets.token_hex` | Deterministic counter |
| Sleep while waiting for a lock holder | `asyncio.sleep` | A coroutine that records calls and optionally writes the awaited value |

Never call `time.sleep` or `asyncio.sleep` with real durations to "wait for
expiry". Advance the fake clock instead.

## Layer the suites

1. **Unit tests with fakes.** The
   [in-memory cache](../assets/memory_cache.py.template) implements the same
   port as the Redis adapter, including TTL, bounded size, and the
   set-if-absent lock. Use it for application and cache-aside logic
   ([test_cache_aside.py.template](../assets/test_cache_aside.py.template),
   [test_memory_cache.py.template](../assets/test_memory_cache.py.template)).
2. **Contract tests.** One parametrized suite runs against both the fake and
   a real Redis-compatible server
   ([test_cache_contract.py.template](../assets/test_cache_contract.py.template)).
   This proves the fake behaves like the server for the operations you use:
   TTL expiry, missing keys, `get_many` ordering, delete counts, lock
   ownership.
3. **HTTP tests.** Conditional requests through the app factory
   ([test_etag.py.template](../assets/test_etag.py.template)): 200 with
   validators, 304 on match, policy headers on errors.
4. **Static checks.** Run the
   [usage checker](../assets/check_cache_usage.py) in CI on the source tree.

## Real server for contract tests

- Start a disposable server from the
  [compose template](../assets/compose.cache.yaml.template) or a
  Testcontainers fixture, and pass its URL through an environment variable
  such as `CACHE_TEST_URL`.
- Mark the real-server tests (for example `@pytest.mark.integration`) and
  skip them with a clear reason when the variable is absent locally; CI must
  set it so the contract suite always runs somewhere.
- Use a unique key prefix per test (`f"test:{uuid4().hex}:"`) and delete it
  afterwards, so parallel test workers can share one server. Never run
  `FLUSHALL` against a shared server.
- Real-server TTL tests may need to observe expiry. Use millisecond TTLs and
  poll `PTTL` or the value with a bounded loop instead of fixed sleeps, or
  limit real-server checks to "TTL is set and positive".
- Test against the server you deploy (Redis or Valkey, matching major
  version); see [redis-clients.md](redis-clients.md).

## What to assert

### Cache-aside behavior

- A miss calls the loader once and stores the encoded value with a TTL inside
  the jitter bounds.
- A hit does not call the loader.
- A "not found" result is cached with the negative TTL and returned as
  `None` without calling the loader again until it expires.
- Loader errors are not cached; the next call retries the loader.
- `invalidate` removes the entry so the next call loads fresh data.
- Keys include namespace, version, and tenant; two tenants never share an
  entry.
- An undecodable stored value is treated as a miss and replaced.

### Stampede protection

- **Single flight in one process.** Start several concurrent `get` calls
  whose loader waits on an `asyncio.Event`, release the event, and assert
  the loader ran once and every caller received the value. No sleeps are
  needed: `asyncio.gather` plus the event gives a deterministic
  interleaving.
- **Cancellation.** Cancelling one waiter does not cancel the shared load;
  the others still receive the value.
- **Distributed lock contention.** With a fake lock that reports "held",
  the loader is not called while the value appears in the cache during the
  wait; when it never appears, the loader runs after the bounded wait
  (fallback), proving no request blocks forever.
- **Lock ownership.** Releasing with a different token does not delete
  another holder's lock (contract test against the real server).

### Failure policy

- A cache that raises `CacheUnavailableError` on every call still returns
  loader results; the request does not fail.
- A failing cache write does not fail the request.
- Timeouts are enforced by the adapter: a fake client that never responds
  produces `CacheUnavailableError` within the configured budget (use a tiny
  budget and an awaitable that never completes, not a real sleep).

### In-process caches

- Module-level `functools` caches are cleared between tests with an
  autouse fixture calling `cache_clear()`; otherwise one test's results leak
  into the next.
- Assert `cache_info()` hits and misses where hit behavior matters.
- TTL caches built on `cachetools` accept a `timer`; pass a fake clock.

## Fixtures pattern

```python
from collections.abc import Iterator

import pytest

from shop.settings import get_settings


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture(autouse=True)
def _clear_memoized() -> Iterator[None]:
    yield
    get_settings.cache_clear()
```

Async tests need an async test runner (the AnyIO pytest plugin or
`pytest-asyncio`); use one consistently across the project.

## Load and chaos checks (optional tier)

- Replay production-like traffic against a cold cache and watch source
  load, p99 latency, and lock contention; this is where stampede protection
  proves itself.
- Stop the cache server mid-run and confirm the service stays available with
  bounded latency and that the circuit breaker opens and closes.
- These belong in a separate performance tier, not in unit runs.

## Sources

- pytest fixtures: <https://docs.pytest.org/en/stable/how-to/fixtures.html>
- Python `asyncio` synchronization primitives (`Event`, `Lock`):
  <https://docs.python.org/3/library/asyncio-sync.html>
- Python `asyncio` tasks (`gather`, `shield`, cancellation):
  <https://docs.python.org/3/library/asyncio-task.html>
- Python `unittest.mock`: <https://docs.python.org/3/library/unittest.mock.html>
- Python `functools` (`cache_clear`, `cache_info`):
  <https://docs.python.org/3/library/functools.html>
- Testcontainers for Python:
  <https://testcontainers-python.readthedocs.io/en/latest/>
- Docker Compose services and health checks:
  <https://docs.docker.com/reference/compose-file/services/>
