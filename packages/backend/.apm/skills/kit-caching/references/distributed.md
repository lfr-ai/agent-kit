# Distributed caching patterns

Verified as of 2026-10-27 against the Redis and Valkey command and
reference documentation listed under Sources. Commands named here exist in
both Redis and Valkey unless stated otherwise.

A shared cache (Redis, Valkey, or a managed equivalent) gives all replicas
one copy of a value. It adds a network hop, a serialization step, and a
dependency that can fail. This reference covers the application side; the
[client reference](redis-clients.md) covers connections and products.

## Choose an access pattern

| Pattern | Read path | Write path | Use when | Watch out for |
| --- | --- | --- | --- | --- |
| Cache-aside (lazy loading) | App reads cache; on miss loads source and stores | App writes source, then deletes the key | Default for most reads | Race between a slow reader and a writer (see invalidation) |
| Read-through | Cache library loads on miss through a registered loader | As cache-aside | You want one loader per namespace behind a port | Hides loader latency; still needs invalidation |
| Write-through | Reads hit a warm cache | App writes source and cache in the same operation | Read-heavy data that must be warm after a write | Writes cost two round trips; a failed cache write leaves stale data unless you delete instead |
| Write-behind (write-back) | Reads from cache | App writes cache; a worker flushes to the source later | Absorbing write bursts for counters or telemetry | Data loss on cache failure; the cache becomes a system of record and needs persistence and replay |
| Refresh-ahead | Serves cached value, refreshes before expiry | As cache-aside | Hot keys with expensive loaders | Refreshing keys nobody reads anymore |

Cache-aside with delete-on-write is the baseline in the
[cache-aside template](../assets/cache_aside.py.template). Write-behind is a
queueing problem, not a caching one; treat it with the same rigor as a
message queue (`kit-task-queue`) or avoid it.

## Design keys

A key is an API. Make it predictable, bounded, and safe:

```text
<app>:<namespace>:v<schema-version>:<tenant>:<entity>:<id>[:<variant>]
shop:catalog:v3:t-42:product:981
shop:catalog:v3:t-42:product-list:sha256=4be2...  # hashed normalized query
```

- **Namespace and version first.** The application prefix lets an ACL
  restrict the service to its own keys. The schema version is bumped when
  the serialized shape changes, so old and new code never decode each
  other's values during a rolling deploy.
- **Tenant isolation is part of the key.** Put the tenant (and user, for
  per-user data) in every key that holds tenant data. Never rely on the
  entity id alone being globally unique.
- **Normalize variants.** Sort query parameters, lower-case case-insensitive
  fields, drop defaults, and include only parameters that change the
  result. Two equivalent requests must produce one key.
- **Hash long or user-influenced parts.** Replace free text and long
  parameter sets with a SHA-256 hex digest of their canonical JSON. Keep a
  readable prefix for debugging. Never put raw personal data or secrets in
  keys; keys appear in monitoring tools and slow logs.
- **Bound the key space.** If a key part comes from the caller, validate its
  shape and length before it becomes a key.
- **Cluster slots.** In Redis Cluster, multi-key commands (`MGET`, `UNLINK`
  with several keys, Lua scripts touching several keys) fail with a
  cross-slot error unless all keys hash to one slot. A hash tag (the part in
  braces, as in `shop:{t-42}:cart`) forces co-location; use it sparingly
  because it concentrates load on one shard.

## Serialize values safely

| Codec | Pros | Cons |
| --- | --- | --- |
| JSON (`json`, stdlib) | Readable, interoperable, safe to decode | Larger; no bytes, dates, or decimals without a convention |
| MessagePack | Compact, fast, binary-safe | Third-party; extension types need a shared convention |
| `pickle` | Any Python object | **Never for data read from a shared store** |

The `pickle` documentation warns that malicious pickle data can execute
arbitrary code during unpickling. Anyone who can write to the cache (a
compromised neighbor service, an operator mistake, a shared instance) could
then run code in every reader. The [usage checker](../assets/check_cache_usage.py)
flags `pickle` loads in modules that import a Redis-compatible client.

Wrap values in an envelope so evolution is explicit:

- A one-byte marker distinguishes a value from a cached negative result.
- The schema version in the key (or envelope) lets readers reject old data.
- Optional compression (for example `zlib`) above a size threshold, marked
  in the envelope.
- A decode failure is a miss: delete the key, log once with the namespace
  (not the value), and load from the source.

Cache plain data transfer shapes (dataclasses or Pydantic models converted
to dictionaries), not ORM objects, sessions, or framework responses.

## Expiry and jitter

- Always set a TTL (`SET key value PX <ms>`). Keys without a TTL survive
  forever and are ignored by `volatile-*` eviction policies.
- Add random jitter so keys written in a burst (deploy, cache flush, batch
  job) do not expire together. Plus or minus 10 percent of the TTL is a
  reasonable start.
- Use absolute expiry by default. Sliding expiry (resetting TTL on read)
  keeps hot but stale data alive forever unless writes invalidate it.
- Prefer `SET ... PX` with the value in one command over `SET` then
  `EXPIRE`, which leaves a window without TTL if the second call fails.

## Prevent stampedes

A stampede (dog-piling) happens when a popular key expires and many
requests miss at once, each recomputing the same value and overloading the
source. Layer the defenses:

1. **In-process single flight.** Within one process, only one task loads a
   key; the others await the same task. This removes duplicates per replica
   and is always worth having.
2. **Distributed lock per key.** Across replicas, the first loader acquires
   `SET lock:<key> <random-token> NX PX <lock-ttl-ms>`. Others poll the cache
   for a bounded time, then fall back to loading themselves (availability
   wins over strict de-duplication). Release only if the token matches,
   atomically, with a short Lua script:

   ```lua
   if redis.call("get", KEYS[1]) == ARGV[1] then
       return redis.call("del", KEYS[1])
   end
   return 0
   ```

   The lock TTL must exceed the loader's p99 duration; otherwise the lock
   expires mid-load and a second loader starts. This lock is an
   optimization: a lost lock only causes duplicate work. Do not reuse it for
   correctness-critical mutual exclusion; the Redis distributed-locks page
   explains the extra guarantees (and costs) that would require.
3. **Probabilistic early expiration.** Each reader may recompute before
   expiry with a probability that rises as expiry approaches and with the
   cost of the computation. Store the value with its expiry `t_exp` and the
   measured compute time `delta`; recompute when
   `now - delta * beta * ln(u) >= t_exp` for a uniform `u` in `(0, 1]` and
   `beta` around 1 (larger favors earlier refresh). This spreads refreshes
   without locks.
4. **Stale-while-revalidate.** Keep a soft expiry in the envelope and a
   longer hard TTL on the key. After the soft expiry, serve the stale value
   and trigger one background refresh (single flight). Only use it where
   the consistency budget allows the stale window.

Warm critical keys after deploys or flushes with a rate-limited job instead
of letting live traffic do it.

## Cache negative results carefully

Repeated lookups for missing records (typos, deleted ids, scanners) hit the
source every time. Cache "not found" with a short TTL (seconds to a minute)
using the envelope marker. Rules:

- Cache only definitive absence (the source answered "no such record").
  Never cache timeouts, errors, or partial results.
- Use a separate, shorter TTL than for values so newly created records
  appear quickly, and delete the key on create as on update.
- Bound the negative key space; an enumeration attack should not fill the
  cache. Validate id format before lookup.

## Invalidate deliberately

TTL is the backstop; invalidation keeps data fresh within the budget.

- **Delete on write, after commit.** Write the source, commit, then
  `UNLINK` (non-blocking delete) the affected keys. Deleting before the
  commit lets a concurrent reader repopulate the old value. Deleting is
  safer than writing the new value, because two writers racing to `SET`
  can leave the older value last.
- **Know the remaining race.** A reader that loaded the old value before the
  write can still store it after your delete. Bound it with the TTL, a
  short delayed second delete, or versioned keys.
- **Reliable invalidation.** If missing an invalidation is unacceptable,
  record it in the same transaction as the write (transactional outbox) and
  let a worker delete keys with retries.
- **Versioned keys.** Keep a version per entity or namespace (`INCR
  shop:catalog:version`), include it in keys, and bump it to invalidate a
  whole group at once. Old keys expire on their own; budget memory for the
  overlap.
- **Broadcast for in-process layers.** Publish an invalidation message on a
  channel; each process evicts its local copy. Redis pub/sub is fire and
  forget: a disconnected subscriber misses messages, so local TTLs must
  still bound staleness.
- **Tags.** To invalidate everything related to a product, add each key to a
  set (`SADD shop:tag:product:981 <key>`) and on change `SMEMBERS` then
  `UNLINK` the members and the set. Give tag sets a TTL at least as long as
  their members and expect cross-slot issues in clusters.
- **Never `KEYS` in production.** It blocks the server. Use `SCAN` with a
  `MATCH` pattern only for maintenance jobs, and prefer versioned keys for
  bulk invalidation.

## Handle hot keys and big values

- A single very hot key concentrates load on one node. Add a short
  in-process L1 for it, or replicate it under several suffixes
  (`...:product:981#0` to `#3`) and read one at random.
- Commands run on a single thread per shard, so large values (hundreds of
  KB or more) increase latency for everyone. Compress, split, cache a
  smaller projection, or keep large blobs in object storage and cache a
  reference.
- Prefer `MGET` or pipelines for batches instead of one round trip per key.

## Configure eviction and memory

Set `maxmemory` and an eviction policy on any instance used as a cache. The
documented policies include `noeviction`, `allkeys-lru`, `allkeys-lfu`,
`allkeys-random`, `volatile-lru`, `volatile-lfu`, `volatile-random`, and
`volatile-ttl`; recent Redis releases also document `allkeys-lrm` and
`volatile-lrm` (least recently modified), so confirm what your server
version supports.

- With `noeviction`, writes fail with an error once memory is full.
- For a dedicated cache, `allkeys-lru` is the documented general default;
  `allkeys-lfu` suits a stable popular subset.
- `volatile-*` policies evict only keys with a TTL and behave like
  `noeviction` when no key has one. Mixing cache keys with durable data in
  one instance is fragile; prefer a dedicated cache instance.
- Persistence (RDB/AOF) is usually unnecessary for a pure cache and adds
  latency spikes; a cold start is acceptable by design.

## Treat the cache as optional

Unless the cache is deliberately the system of record, a cache failure must
degrade performance, not availability:

- **Short timeouts.** Cache operations get a budget far below the source
  latency (tens of milliseconds on a local network). A slow cache is worse
  than no cache.
- **At most one retry** for reads; none on the request path for writes.
  Retries, backoff, and circuit-breaker mechanics are owned by
  `kit-python-service`.
- **Circuit breaker.** After repeated failures, skip the cache for a cool-down
  period instead of paying the timeout on every request.
- **Fallback to source**, with a concurrency limit on the loader so a cold or
  absent cache does not overload the database.
- **Never fail a request because a cache write failed.** Log and continue.
- **Readiness** does not depend on an optional cache; report it as degraded
  in diagnostics instead.
- Map client exceptions to one `CacheUnavailableError` at the adapter so
  the application handles one failure type
  ([Redis adapter](../assets/redis_cache.py.template)).

## Measure

| Signal | Source | Use |
| --- | --- | --- |
| Hits, misses, hit ratio per namespace | Application counters | Is the cache paying for itself? |
| Get/set latency p50/p99 | Application histograms | Detect slow cache or network |
| Errors and timeouts | Application counters | Trip alerts and breaker tuning |
| Loader calls and duration | Application metrics | Stampedes and source load |
| Lock acquired/contended/fallback | Application counters | Stampede protection health |
| `evicted_keys`, `expired_keys`, `keyspace_hits`, `keyspace_misses` | `INFO stats` | Memory pressure and server-side ratio |
| `used_memory`, `maxmemory` | `INFO memory` | Capacity planning |

Label metrics by namespace, never by raw key: keys are high-cardinality and
may contain identifiers. Dashboards and alerts belong to
`kit-observability`.

## Secure the store

- Connect with TLS (`rediss://`) outside a local development network.
- Use a dedicated ACL user per service, restricted to its key prefix and
  the commands it needs, for example
  `ACL SETUSER shop-api on >... ~shop:* &shop:* +@read +@write +@scripting -@dangerous`.
  Adjust categories to what the adapter actually calls.
- Keep passwords and connection URLs in the secret provider (`kit-config`);
  log the host, never the URL with credentials.
- Do not store data in the cache that the service could not otherwise
  read; the cache must not widen access between tenants or services.

## Sources

- Redis `SET` command: <https://redis.io/docs/latest/commands/set/>
- Redis distributed locks:
  <https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/>
- Redis `EVAL` and scripting: <https://redis.io/docs/latest/commands/eval/>
- Redis `UNLINK`: <https://redis.io/docs/latest/commands/unlink/>
- Redis `SCAN`: <https://redis.io/docs/latest/commands/scan/>
- Redis `MGET`: <https://redis.io/docs/latest/commands/mget/>
- Redis pub/sub: <https://redis.io/docs/latest/develop/interact/pubsub/>
- Redis key eviction: <https://redis.io/docs/latest/develop/reference/eviction/>
- Redis `INFO`: <https://redis.io/docs/latest/commands/info/>
- Redis ACL:
  <https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/>
- Redis cluster scaling and hash slots:
  <https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/>
- Valkey `SET`: <https://valkey.io/commands/set/>
- Valkey key eviction: <https://valkey.io/topics/lru-cache/>
- Python `pickle` security warning: <https://docs.python.org/3/library/pickle.html>
- Microsoft Azure Architecture Center, cache-aside pattern:
  <https://learn.microsoft.com/azure/architecture/patterns/cache-aside>
- Vattani, Chierichetti, Lowenstein, "Optimal Probabilistic Cache Stampede
  Prevention", PVLDB 8(8), 2015 (origin of the early-expiration formula):
  <https://www.vldb.org/pvldb/vol8/p886-vattani.pdf>
