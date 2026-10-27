---
name: kit-caching
description: Use when adding or reviewing in-process, Redis-compatible, or HTTP response caching and its invalidation.
license: MIT
---

# Cache deliberately, invalidate explicitly, degrade safely

## Procedure

1. Decide whether to cache at all with the
   [decision guide](references/decision-guide.md): measure call rate, source
   latency, distinct keys, and payload size; fix missing indexes or N+1
   queries first; never cache values that decide money, stock, or access.
2. Write the consistency budget per data class (maximum staleness,
   read-your-writes needs, behavior when the cache is down) and pick the
   outermost correct layer: memoization, per-process TTL, shared
   Redis-compatible cache, or HTTP caching. Hand edge, gateway, and model
   caching to `kit-edge-networking`, `kit-api-gateway`, and
   `kit-llm-gateway`.
3. For in-process caches follow [in-process caching](references/in-process.md):
   bound every `lru_cache`, never decorate instance methods or `async def`
   with `functools` caches, return immutable values, and use an injected
   clock for TTL caches.
4. For a shared cache, depend on the [cache ports](assets/cache_port.py.template)
   (`Cache`, `DistributedLock`, `Codec`, `CacheUnavailableError`) and load the
   [settings facet](assets/cache_settings.py.template) through the project's
   settings class (`kit-config`). The URL carries no credentials, TLS is
   required outside local development, and timeouts stay far below the
   source latency.
5. Create one client per process in the lifespan with the
   [Redis adapter](assets/redis_cache.py.template) and close it on shutdown;
   see [Redis-compatible clients](references/redis-clients.md) for timeouts,
   retries, TLS, ACL users, cluster mode, Valkey, licensing, and managed
   service status.
6. Read through the [cache-aside loader](assets/cache_aside.py.template):
   keys `prefix:namespace:v<version>:tenant:...`, JSON or another data-only
   codec, jittered TTLs, short negative caching, in-process single flight,
   and an optional distributed lock with a bounded wait. Apply the patterns
   in [distributed caching](references/distributed.md).
7. Invalidate on every write path after commit (`UNLINK`, versioned keys,
   or tags); use an outbox when a missed invalidation breaks the budget.
   Keep the TTL as the backstop.
8. Treat the cache as optional: map client errors to
   `CacheUnavailableError`, fall back to the source, never fail a request
   because a cache write failed, and keep readiness independent of an
   optional cache. Resilience mechanics come from `kit-python-service`.
9. For HTTP responses apply [HTTP caching semantics](references/http-caching.md)
   with the [ETag helper](assets/etag.py.template): explicit
   `Cache-Control` on every response, `private` or `no-store` for per-user
   data, strong ETags, weak `If-None-Match` comparison, correct 304 headers,
   and `Vary` on negotiated headers.
10. Use the [in-memory cache](assets/memory_cache.py.template) as the test
    fake and local L1. Copy the tests per [testing caches](references/testing.md):
    [memory cache](assets/test_memory_cache.py.template),
    [cache-aside](assets/test_cache_aside.py.template),
    [contract suite](assets/test_cache_contract.py.template) against the fake
    and a real server, and [conditional GET](assets/test_etag.py.template).
    Start the server with the [compose file](assets/compose.cache.yaml.template).
11. Emit hit, miss, error, load, and lock events per namespace (never per raw
    key) and hand dashboards and alerts to `kit-observability`.
12. Run [check_cache_usage.py](assets/check_cache_usage.py) on the source
    tree, then the project gate.

```text
python check_cache_usage.py src/shop
python check_cache_usage.py src/shop --allow-unbounded "*/settings.py" --exclude migrations
python check_cache_usage.py src/shop --rule pickle-redis
python check_cache_usage.py --self-test
```

The checker reports `method-cache`, `async-cache`, `unbounded-cache`, and
`pickle-redis` as `path:line: [rule] message` and exits 0 clean, 1 with
findings, 2 on usage or input errors. Mark a reviewed line with
`# cache-usage: reviewed`. It parses source only; it does not prove hit
ratios, invalidation, or runtime behavior.

## Acceptance gates

- A written consistency budget exists for each cached data class, with the
  chosen layer, TTL, negative TTL, and unavailable-cache behavior.
- Every cache is bounded by entries or memory; the checker reports no
  unreviewed findings, and no `pickle` decoding exists near a shared store.
- Keys include prefix, namespace, schema version, and tenant; caller input
  in keys is validated or hashed; no secrets or raw personal data in keys.
- Every write path that changes cached data invalidates after commit, and a
  test proves the next read is fresh.
- With the cache down, requests still succeed within the latency budget;
  tests cover unavailable reads and failed writes.
- Concurrent misses for one key call the loader once per process, and the
  distributed lock wait is bounded with a fallback.
- The contract suite passes against the fake and against the deployed server
  type (Redis or Valkey) in CI.
- Every HTTP response has an explicit `Cache-Control`; per-user or
  credentialed responses are never shareable; 304 responses repeat
  `ETag`, `Cache-Control`, and `Vary` without a body.
- Hit ratio, latency, errors, and evictions are observable per namespace.
