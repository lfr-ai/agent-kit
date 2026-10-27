# In-process caching in Python

Verified as of 2026-10-27 against the Python 3.13 documentation and the
`cachetools` 7.x documentation.

In-process caches live in one interpreter. Every worker process and every
replica has its own copy, nothing is shared, and nothing survives a restart.
That makes them the cheapest and the least coordinated layer.

## `functools.cache` and `functools.lru_cache`

Facts from the standard library documentation:

- `lru_cache(maxsize=128, typed=False)` keeps up to `maxsize` most recent
  results. `maxsize=None` disables eviction, so the cache grows without
  bound. `functools.cache` is the same as `lru_cache(maxsize=None)` with a
  thinner wrapper.
- Arguments must be hashable because results are stored in a dictionary.
  `f(a=1, b=2)` and `f(b=2, a=1)` may be cached as separate entries.
- `typed=True` caches arguments of different types separately (`1` and
  `1.0`); type specificity applies only to immediate arguments, not to the
  contents of a tuple argument.
- The wrapper exposes `cache_info()` (hits, misses, maxsize, currsize),
  `cache_clear()`, `cache_parameters()`, and `__wrapped__` for bypassing the
  cache.
- The cache is thread-safe in the sense that its data structure stays
  coherent, but the wrapped function can run more than once for the same
  arguments if another thread calls before the first result is stored.
- The cache keeps references to arguments and return values until they are
  evicted or cleared.
- It makes no sense to cache functions with side effects, functions that
  must return a distinct mutable object per call (generators, async
  functions), or impure functions such as `time()` or `random()`.

There is no time-to-live. A memoized value is valid until eviction, an
explicit `cache_clear()`, or process exit.

### Good uses

- Pure computations on small hashable inputs (parsing, normalization).
- Zero-argument factories evaluated once per process, such as loading
  validated settings (`@cache def get_settings() -> Settings`). A
  zero-argument function holds at most one entry, so `cache` is bounded.
- Compiled regular expressions, templates, or schema objects built from
  constant inputs.

### Bad uses

- Anything reading the database, the network, the clock, or the
  environment after start-up: the result goes stale and never refreshes.
- Functions taking request data, user identifiers, or other unbounded keys
  with `maxsize=None`: an unbounded memory leak keyed by traffic.
- Returning mutable objects: every caller shares and can mutate the same
  list or dict. Return tuples, `frozenset`, or frozen dataclasses.

### Size the bound

Choose `maxsize` from the working set, not from habit. Multiply the bound by
the average entry size and by the number of worker processes per host:
`maxsize=10_000` entries of 20 KB in 8 workers is about 1.6 GB.
`sys.getsizeof` is shallow, so measure a representative value with
`tracemalloc` when entries are large. Track `cache_info()` in a periodic
metric or debug endpoint to see whether the hit ratio justifies the memory.

## Do not decorate instance methods

`@lru_cache` on a method caches at class level, and the documentation notes
that `self` becomes part of every key. Consequences:

- Every instance that was ever called stays alive until its entries age out
  or the cache is cleared, which holds connections, sessions, or large
  buffers longer than intended.
- All instances share one `maxsize`, so a busy instance evicts the entries
  of another.
- `self` must be hashable; a mutable object whose `__eq__`/`__hash__` do not
  reflect the fields the method depends on silently returns stale values.

The Python programming FAQ ("How do I cache method calls?") describes the
trade-off between `cached_property` (instance-level, released with the
instance, no arguments) and `lru_cache` (class-level, bounded, keeps
instances alive). Prefer, in order:

1. A module-level function cached on the immutable values it really depends
   on, called from the method: `return _rate_for(self.currency, day)`.
2. `functools.cached_property` for an argument-free derived value of an
   effectively immutable object (see below).
3. A per-instance cache created in `__init__`, for example
   `self._lookup = lru_cache(maxsize=256)(self._lookup_uncached)`. This
   creates a reference cycle (instance, wrapper, bound method) that the
   garbage collector reclaims, so it is acceptable for long-lived service
   objects but wasteful for many short-lived instances.

`@staticmethod` functions have no `self` and behave like module functions.
A cached `@classmethod` keys on the class object, which normally lives for
the whole process, so it does not leak instances; the bundled checker
exempts both.

## Never memoize `async def` with `functools`

Calling an `async def` function returns a coroutine object. `lru_cache`
stores that object, and the second caller receives the same, already
awaited coroutine, which raises `RuntimeError: cannot reuse already awaited
coroutine`. `cached_property` on an `async def` has the same problem.

For asynchronous memoization, cache the *result* or share one in-flight
task per key (single flight):

```python
import asyncio
from collections.abc import Awaitable, Callable


class AsyncMemo[K, V]:
    """Share one in-flight load per key and keep completed results."""

    def __init__(self, load: Callable[[K], Awaitable[V]], *, max_entries: int) -> None:
        self._load = load
        self._max_entries = max_entries
        self._done: dict[K, V] = {}
        self._pending: dict[K, asyncio.Task[V]] = {}

    async def get(self, key: K) -> V:
        if key in self._done:
            return self._done[key]
        task = self._pending.get(key)
        if task is None:
            task = asyncio.ensure_future(self._load(key))
            self._pending[key] = task
            task.add_done_callback(lambda done: self._settle(key, done))
        return await asyncio.shield(task)

    def _settle(self, key: K, task: asyncio.Task[V]) -> None:
        self._pending.pop(key, None)
        if task.cancelled() or task.exception() is not None:
            return
        if len(self._done) >= self._max_entries:
            self._done.pop(next(iter(self._done)))
        self._done[key] = task.result()
```

Key points: the dictionary holds a strong reference to the task (the event
loop only keeps weak references), `asyncio.shield` stops one cancelled
caller from cancelling the shared load, and failures are not cached. Add a
TTL by storing an expiry next to the value, as the
[cache-aside template](../assets/cache_aside.py.template) does.

## `functools.cached_property`

- Computes the value on first attribute access and stores it in the
  instance `__dict__` under the same name; later reads are plain attribute
  reads. Deleting the attribute clears it; assigning overrides it.
- Requires a mutable instance `__dict__`. Classes that define `__slots__`
  without `__dict__` cannot use it; this includes
  `@dataclass(frozen=True, slots=True)` records, which Agent Kit recommends
  for immutable values. For those, compute the derived value in
  `__post_init__` into a `field(init=False)` with `object.__setattr__`, or
  call a module-level cached function.
- It interferes with key-sharing instance dictionaries (PEP 412), so many
  instances use more memory.
- Since Python 3.12 it has no internal lock. Under threads the getter can
  run more than once per instance and the last result wins. This is fine
  for idempotent computations; add your own lock otherwise.
- Use it only on effectively immutable objects; it cannot notice that the
  attributes it was computed from changed.

## TTL caches with `cachetools`

`cachetools` (third-party) provides `TTLCache(maxsize, ttl, timer=time.monotonic)`,
`LRUCache`, `LFUCache`, and `TLRUCache` (per-item time-to-use). Facts from
its documentation:

- The cache classes are not thread-safe. Synchronize access, typically with
  the `cached(cache, lock=threading.Lock())` decorator.
- The lock only guards cache access; the wrapped function runs outside the
  lock, so concurrent misses can call it more than once. The `condition`
  parameter (a `threading.Condition`) lets waiting callers block until the
  first computation finishes, which mitigates stampedes.
- Expired items are removed lazily (for example on the next insert) and
  can still hold memory; `expire()` removes them explicitly.
- `getsizeof` makes `maxsize` a size budget instead of an item count.
- The `timer` parameter accepts any clock, which makes tests deterministic.

```python
import threading

from cachetools import TTLCache, cached

_RATES: TTLCache[str, float] = TTLCache(maxsize=1_024, ttl=30)


@cached(_RATES, lock=threading.Lock())
def exchange_rate(currency: str) -> float:
    return _fetch_rate(currency)
```

These decorators wrap synchronous functions. In asyncio code use an
asynchronous cache with explicit locks, such as the in-memory adapter in
[memory_cache.py.template](../assets/memory_cache.py.template) combined with
the single-flight loader.

## Process model reminders

- Pre-fork servers (Gunicorn, multiple Uvicorn workers) give each worker an
  independent cache; a value cached before forking is copied into each child
  and diverges afterwards.
- `cache_clear()` in one worker does not affect the others. Invalidation
  that must reach every process needs a shared cache or a broadcast
  (see [distributed.md](distributed.md)).
- Tests must clear module-level caches between cases (an autouse fixture
  calling `cache_clear()`), or results leak across tests; see
  [testing.md](testing.md).

## Sources

- Python `functools` documentation:
  <https://docs.python.org/3/library/functools.html>
- Python programming FAQ, "How do I cache method calls?":
  <https://docs.python.org/3/faq/programming.html>
- Python `asyncio` tasks (strong references, `shield`):
  <https://docs.python.org/3/library/asyncio-task.html>
- Python `asyncio` synchronization primitives:
  <https://docs.python.org/3/library/asyncio-sync.html>
- `cachetools` documentation: <https://cachetools.readthedocs.io/en/latest/>
