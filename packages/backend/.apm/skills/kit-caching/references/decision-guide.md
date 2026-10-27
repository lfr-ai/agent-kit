# Decide whether, where, and how long to cache

Verified as of 2026-10-27. This reference contains no vendor product facts;
version-sensitive client and service facts live in
[redis-clients.md](redis-clients.md).

A cache trades freshness and operational complexity for latency and load.
Every cache entry is a copy that can be wrong. Start from the question
"what is the cheapest way to make this read fast enough and correct enough?"
and treat caching as one answer, not the default answer.

## Do not cache when

- **The source is already fast enough.** Measure first. A 2 ms indexed
  lookup does not need a network cache whose round trip costs 0.5 to 1 ms
  plus serialization and a new failure mode.
- **The real defect is in the source.** Missing indexes, N+1 queries,
  unbounded result sets, and chatty remote calls are fixed in the query or
  client, not hidden behind a cache that will expire at the worst moment.
- **The value decides money, stock, or access.** Balances, reservation
  counts, idempotency records, authorization decisions, and revocation
  lists need the source of truth or a purpose-built store with explicit
  consistency, not a best-effort copy.
- **Reuse is low.** If almost every request uses a distinct key (search
  queries with free text, per-request tokens), the hit ratio stays near zero
  while memory and write load grow.
- **The key space is unbounded and attacker-controlled.** Caching on raw
  query strings or headers lets a client fill memory or evict useful
  entries. Normalize and bound the key, or do not cache.
- **Writes dominate reads.** When data changes more often than it is read,
  invalidation traffic exceeds the savings.
- **The value is a secret.** Tokens, passwords, and signing keys belong in
  the secret provider with its own rotation. A cache may hold an opaque
  reference, never the secret material, unless the cache itself is the
  documented session store with matching protection.
- **Read-your-writes is required and invalidation is not reliable.** If a
  user must see their own change immediately, either invalidate in the same
  unit of work (and accept that invalidation can fail) or bypass the cache
  for that user's subsequent reads.

## Measure before choosing

Record these numbers for the candidate read path before writing code:

| Measurement | Why it matters | How to get it |
| --- | --- | --- |
| Call rate (per second, peak) | Upper bound on savings | Request metrics or traces |
| Source latency p50/p99 | Savings per hit | Traces around the loader |
| Distinct keys per window | Predicts hit ratio and memory | Log a hashed key sample |
| Payload size p50/max | Memory, network, serialization cost | Encode a sample |
| Acceptable staleness | Sets the TTL ceiling | Product owner decision |
| Write rate per key | Invalidation cost | Write-path metrics |

A rough expected hit ratio is `1 - distinct_keys / calls` over a window no
longer than the TTL. Below about 50 percent, a shared network cache rarely
pays for itself unless the source is very slow or rate-limited.

## Choose the layer

| Layer | Scope | Typical use | Consistency | Invalidation | Failure mode |
| --- | --- | --- | --- | --- | --- |
| Memoization (`functools.cache`, `lru_cache`) | One process, forever or LRU | Pure functions, parsed configuration, compiled patterns | Exact for pure inputs | `cache_clear()` or restart | Memory growth; stale if not pure |
| Per-process TTL cache | One process, bounded time | Reference data, remote lookups tolerating seconds of staleness | Divergent per replica | TTL only (or local hooks) | Replicas disagree for up to one TTL |
| Shared Redis-compatible cache | All replicas | Expensive queries, aggregates, remote API results | One copy, staleness bounded by TTL and invalidation | Delete on write, versioned keys, pub/sub, tags | Network hop; cache outage must not take down the service |
| HTTP caching (browser, proxy, CDN) | Clients and intermediaries | Public or per-user GET responses | Controlled by `Cache-Control` and validators | Expiry, revalidation, purge by URL or surrogate key | Stale or leaked responses if headers are wrong |

Pick the outermost layer that is correct for the data. A public catalog page
with a validator is cheapest to serve from HTTP caches; a per-user dashboard
cannot be shared at the edge but can use `private` browser caching plus a
shared application cache keyed by tenant and user.

### Two-level caches

A per-process L1 in front of a shared L2 removes the network hop for hot
keys. Rules for keeping it honest:

1. L1 TTL is much shorter than L2 TTL (for example 5 seconds versus 5
   minutes) because L1 has no cross-replica invalidation by default.
2. If writes must be visible within less than the L1 TTL, publish an
   invalidation message (see [distributed.md](distributed.md)) and evict L1
   on receipt, or do not use L1 for that data.
3. L1 is bounded by entry count and, for large values, by an estimated
   byte size.
4. Metrics separate L1 and L2 hits so a falling L2 hit ratio is visible.

## Set a consistency budget

Write the budget down per data class before choosing TTLs. The TTL is the
maximum staleness when invalidation fails, not the expected staleness.

| Data class (example) | Max staleness | Strategy |
| --- | --- | --- |
| Product descriptions and images | 10 minutes | Shared cache plus HTTP `max-age`, delete on publish |
| List prices on browse pages | 60 seconds | Shared cache, delete on price change; checkout re-reads source |
| Order status for its owner | 5 seconds or read-your-writes | Short TTL, bypass after the user's own write |
| Feature flags and reference data | 30 seconds | Per-process TTL cache, refreshed in background |
| Authorization decisions | 0 to a few seconds | Prefer no cache; if cached, key by subject and policy version and invalidate on change |
| Aggregated reports | 1 hour | Precompute or cache with versioned keys |

For each class also decide what happens when the cache is unavailable:
serve from source (default), serve stale (only with an explicit stale
budget), or fail (only when the cache is a required system of record, which
means it is no longer "just a cache").

## Size TTLs deliberately

- Start from the consistency budget, then shorten if invalidation is
  missing for any write path.
- Add jitter (for example plus or minus 10 percent) so entries written
  together do not expire together.
- Use a separate, shorter TTL for negative results ("not found") so newly
  created records appear quickly.
- Long TTLs need reliable invalidation and key versioning; short TTLs need
  stampede protection because misses are frequent.

## Ownership across Agent Kit skills

| Concern | Owner |
| --- | --- |
| Application in-process caches, distributed cache adapters, invalidation, stampede control, negative caching, `Cache-Control`/`ETag`/`Vary` produced by the application | `kit-caching` (this skill) |
| Reverse proxy, CDN, and proxy cache configuration; surrogate-key purge wiring; edge rate limits | `kit-edge-networking` |
| API gateway response caching policies, quotas, keys, and products | `kit-api-gateway` |
| LLM response caching and semantic caching in model gateways | `kit-llm-gateway` |
| Application rate limiting and its shared counter store | `kit-fastapi-service` |
| Timeouts, retries with jitter, circuit breakers, bulkheads | `kit-python-service` |
| Settings facets and secret delivery | `kit-config` |
| Cache dashboards, SLOs, and alerts | `kit-observability` |

When a change spans layers (for example application headers plus CDN
configuration), make the application emit correct headers here and hand the
edge configuration to the owning skill by name.

## Decision checklist

- [ ] Baseline latency, call rate, distinct keys, and payload size recorded.
- [ ] The source has been checked for missing indexes and N+1 patterns.
- [ ] Data class, consistency budget, and unavailable-cache behavior written down.
- [ ] Layer chosen with a reason; outer layers considered first.
- [ ] Key space bounded and not attacker-controlled.
- [ ] Every write path that changes the data has an invalidation step, or the
      TTL alone satisfies the budget.
- [ ] Metrics planned: hit ratio, latency per layer, evictions, errors.

## Sources

- Python `functools` documentation:
  <https://docs.python.org/3/library/functools.html>
- Microsoft Azure Architecture Center, caching guidance:
  <https://learn.microsoft.com/azure/architecture/best-practices/caching>
- Microsoft Azure Architecture Center, cache-aside pattern:
  <https://learn.microsoft.com/azure/architecture/patterns/cache-aside>
- RFC 9111, HTTP Caching: <https://www.rfc-editor.org/rfc/rfc9111.html>
- Redis key eviction: <https://redis.io/docs/latest/develop/reference/eviction/>
