---
description: Add or review a cache with a written consistency budget, explicit invalidation, safe degradation, and tests.
argument-hint: Data to cache and why, e.g. "product details read on every catalog page"
agent: agent
---

# Add a cache deliberately

Cache only data with a measured need, a written staleness budget, and an
invalidation path, so a cold or failed cache never changes correctness.

## Input

- The user-supplied argument names the data and the access path to speed up.
  Ask for the current latency, request rate, and acceptable staleness when they
  are not stated and cannot be measured from existing telemetry.

## Procedure

1. Load [kit-caching](../skills/kit-caching/SKILL.md) and follow its decision
   guide first. Measure call rate, source latency, distinct keys, and payload
   size; fix missing indexes, N+1 queries, or chatty calls before caching.
2. Refuse to cache values that decide money, stock, authorization, or
   anything a user must see immediately after writing it, unless the budget
   below explicitly allows staleness.
3. Write the consistency budget: maximum staleness, read-your-writes needs,
   tenant isolation, and behavior when the cache is unavailable.
4. Pick the outermost correct layer: memoization of a pure function, a bounded
   per-process TTL cache, a shared Redis-compatible cache, or HTTP caching.
   Hand CDN or proxy caching to the `kit-edge-networking` skill and gateway
   response caching to the `kit-api-gateway` skill when those layers own it.
5. For a shared cache, depend on the cache port, create the client once in the
   application lifespan, and read through the cache-aside loader with
   versioned, tenant-scoped keys, jittered TTLs, short negative caching, and
   single-flight loading.
6. Add invalidation after commit on every write path that changes the cached
   data; keep the TTL as the backstop.
7. Make the cache optional: map client errors to the unavailable error, fall
   back to the source, and never fail a request because a cache write failed.
8. For HTTP responses, set an explicit `Cache-Control` on every response, use
   `private` or `no-store` for per-user data, and support conditional requests
   with strong ETags.
9. Write tests first: hit, miss, expiry with an injected clock, invalidation
   after a write, concurrent misses loading once, cache unavailable, and the
   contract suite against the fake and a real server.
10. Emit hit, miss, error, and eviction metrics per namespace, never per raw
    key.
11. Run the skill's cache-usage checker on the source tree and the project
    completion gate.

## Acceptance gates

- [ ] The consistency budget and chosen layer are recorded next to the code.
- [ ] Every cache is bounded, and the checker reports no unreviewed findings.
- [ ] Every write path invalidates, and a test proves the next read is fresh.
- [ ] Requests succeed within budget with the cache down.
- [ ] Per-user responses are never stored by shared caches.

## Output

The consistency budget, the chosen layer with the reason, files changed, the
measured or expected effect, and the commands run with results.
