# Application rate limiting

Reviewed 2026-10-23; external facts (draft status, library and server
behavior) re-verified as of 2026-10-27. Templates:
[rate_limit.py.template](../assets/rate_limit.py.template),
[redis_rate_limit.py.template](../assets/redis_rate_limit.py.template), and
[test_redis_rate_limit.py.template](../assets/test_redis_rate_limit.py.template).

## Layering: who limits what

| Layer | Owner | Limits | Key |
| --- | --- | --- | --- |
| Edge (proxy, load balancer, CDN) | `kit-edge-networking` | Connections, request rate per address, body size, slow clients | Client address |
| API gateway or management | `kit-api-gateway` | Consumer quotas, subscription tiers, API keys | Consumer or subscription |
| Application (this skill) | `kit-fastapi-service` | Per user, per tenant, per route, cost-based business limits | Verified subject, tenant, or client address |

Keep the edge limit as the backstop: it protects the application process
before any Python runs. The application limit adds identity and business
context the edge does not have. Do not duplicate gateway quotas in the app;
read the gateway's consumer identity instead when one is present.

## Algorithms

| Algorithm | State per key | Behavior | Trade-off |
| --- | --- | --- | --- |
| Fixed window | One counter | Resets at window boundaries | Allows up to twice the limit across a boundary; simplest |
| Sliding window log | One timestamp per request (sorted set) | Exact count over the last window | Memory and work grow with the limit |
| Sliding window counter | Two counters | Weights the previous window by overlap | Approximate, constant memory, small error at boundaries |
| Token bucket | Tokens and last refill time | Bursts up to capacity, refills at a rate | Two values to update; refill math needs one clock |
| Leaky bucket (queue) | Queue | Smooths output to a constant rate | Adds latency; requests wait instead of failing |
| GCRA | One timestamp (theoretical arrival time) | Equivalent to a token bucket checked at arrival | Constant memory, one read and one write, smooth bursts |

The shared store uses GCRA (generic cell rate algorithm, defined for ATM
traffic in ITU-T I.371). For a policy of `limit` requests per `window`:

- emission interval `T = window / limit`; burst tolerance `tau = window - T`;
- a request at time `now` is admitted when `TAT - tau <= now`, where `TAT` is
  `max(stored TAT, now)`; on admission store `TAT + T`;
- `remaining = floor((tau + T - (new TAT - now)) / T)`;
  `Retry-After = TAT - tau - now`; the quota is fully restored at `TAT`.

So `limit` requests may arrive together, then one per `T`. When the product
needs an exact count over a trailing window (for example billing), use a
sliding window log in a sorted set (`ZADD`, `ZREMRANGEBYSCORE`, `ZCARD` in
one script) and accept memory proportional to the limit. The in-memory store
uses a fixed window and is only for tests and single-process tools.

## Keys and policies

- Key by the verified subject (`sub:<id>`) or tenant after authentication;
  `SubjectRateLimit` runs as a dependency after the `kit-auth` principal
  dependency. Never key by an unverified token claim: the caller can rotate it.
- Before authentication, key by the client address the server resolved.
  Behind a proxy that is correct only when the server trusts forwarded headers
  from the proxy alone (`uvicorn --proxy-headers --forwarded-allow-ips`); see
  `kit-edge-networking`. Otherwise every request shares the proxy address, or
  an attacker spoofs `X-Forwarded-For`.
- Consider IPv6: one client often controls a whole `/64`. Key by the prefix
  when abuse rotates addresses.
- Prefix every key with the policy name so policies never share counters, and
  hash keys before they reach a shared store; addresses and subjects are
  personal data.
- Route policies: `RouteRule` matches a path prefix on segment boundaries and
  optional methods; the longest prefix wins. Expensive or abuse-prone routes
  (login, password reset, search, exports) get their own, smaller policy.
- Cost-based limits: when operations differ in cost (tokens, rows, bytes),
  extend the store with a `cost` argument that advances `TAT` by `cost * T`;
  keep `hit` as the cost-one case.
- Exempt health probes and internal callers by path or verified identity,
  never by a client-supplied header.

## Distributed correctness

- Decide atomically on the server: one Lua script reads and writes the key,
  so concurrent workers cannot both see the last free slot. Redis and Valkey
  run a script without interleaving other commands.
- Read the clock inside the script with `TIME`. Redis 5 made script effects
  replication the default and Redis 7 removed verbatim replication, so `TIME`
  is allowed; replicas receive the resulting `SET`, not the script.
- Touch one key per decision. That keeps the script valid on a cluster
  (all keys of a script must hash to one slot) without hash tags.
- Set a TTL equal to the time until the quota is restored, so idle keys
  disappear and memory stays bounded.
- redis-py `register_script` runs `EVALSHA` and reloads the script after a
  `NOSCRIPT` error (the script cache is lost on restart or failover).
- Bound each decision with a short timeout (the template uses 250 ms) and
  configure `socket_timeout` and `socket_connect_timeout` on the client; a
  slow limiter must not become the outage. New connections and the first
  `NOSCRIPT` reload make cold decisions slower: warm the client in the
  lifespan (for example `await client.ping()`) and size the connection pool
  (`max_connections`) for peak concurrency, or bursts time out and trigger the
  failure mode.
- Failover can lose recent writes, briefly granting extra requests; that is
  acceptable for rate limiting and is not acceptable for billing.
- Several regions with one store add cross-region latency to every request;
  prefer one store per region with a regional quota.

## Failure policy

`FailureMode` has no default in code; the settings facet defaults to `open`.

| Mode | When the store fails | Choose for |
| --- | --- | --- |
| `open` | Request is admitted; warning log and `failed_open` metric | General API traffic, where the edge limit remains |
| `closed` | 503 problem with `Retry-After`; `failed_closed` metric | Credential, payment, or messaging routes where abuse costs more than an outage |

Alert on any `failed_*` outcome; an unnoticed fail-open limiter is no limiter.
The store raises `RateLimitStoreError` (an `OSError`) for timeouts, connection
errors, an unbound client, or a malformed reply; other exceptions are defects
and surface as 500.

## Response headers

- Exceeded quota: `429 Too Many Requests` (RFC 6585) with problem details and
  `Retry-After` in delay-seconds (RFC 9110); the body never echoes the key.
- Draft fields, behind `rate_limit_headers`: the IETF draft
  `draft-ietf-httpapi-ratelimit-headers-11` (May 2026, work in progress,
  expires November 2026) defines structured-field lists:
  `RateLimit-Policy: "default";q=120;w=60` and
  `RateLimit: "default";r=37;t=21`. `q` is the quota, `w` the window, `r`
  the remaining quota, and `t` seconds until it is restored. The template
  omits the optional `pk` partition key so identifiers do not leak. Earlier
  drafts used `RateLimit-Limit`, `RateLimit-Remaining`, and `RateLimit-Reset`;
  do not mix the two styles.
- Expose `Retry-After` and, when enabled, the draft fields through CORS
  `expose_headers` so browser clients can read them.

## Client guidance

Document for API consumers: honor `Retry-After` before retrying; otherwise use
capped exponential backoff with full jitter (`kit-python-service` resilience
reference); treat `RateLimit` values as hints, not guarantees; spread
scheduled jobs instead of starting them on the minute.

## Wiring a shared store

Create the client in the lifespan and bind it; the app factory receives the
unbound store so the middleware exists before startup:

```python
store = RedisRateLimitStore(key_prefix="shop:rl:")


@asynccontextmanager
async def open_container() -> AsyncIterator[Container]:
    client = Redis.from_url(
        settings.redis_url.get_secret_value(),
        socket_connect_timeout=1.0,
        socket_timeout=0.25,
    )
    async with client, store.bind(client):
        yield Container(catalog=catalog)


app = create_app(
    settings=settings.http,
    container_factory=open_container,
    rate_limit_store=store,
)
```

Load the URL as a secret through `kit-config`; use TLS (`rediss://`) and
authentication for any store outside the host.

## Testing

- Unit: drive `InMemoryRateLimitStore` with a fake clock; never sleep.
- HTTP: the [test template](../assets/test_api.py.template) covers 429 with
  `Retry-After`, route policies, draft headers, both failure modes, and the
  per-subject dependency.
- Contract: run the same cases against every store, including concurrent
  `asyncio.gather` hits that must admit exactly `limit` requests.
- Lua: run the Redis cases against a real Redis-compatible container (Redis 7
  or Valkey) through `SHOP_TEST_REDIS_URL` or Testcontainers; a fake client
  cannot prove script atomicity or `TIME` behavior.
- Failure: a store that raises `RateLimitStoreError`, a command timeout, and
  an unreachable server.

## Observability

- Count decisions with a metric labeled by policy and outcome
  (`allowed`, `limited`, `failed_open`, `failed_closed`) through the
  `metric_hook`; never label by key, address, or subject (cardinality and
  privacy, per `kit-observability`).
- Record store latency; alert on `failed_*` and on a sudden rise in `limited`.
- Log store failures once at warning level with the policy and error type.

## Failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Limit is several times too high | In-memory store with several workers | Shared store |
| Every caller limited together | Key is the proxy address | Trust forwarded headers from the proxy only |
| Limit bypassed by rotating tokens | Keyed by unverified claims | Key after verification |
| Outage when the store is slow | No timeout, or fail-closed everywhere | Short timeout; choose the mode per policy |
| Keys never expire | No TTL | TTL equal to the restore time |
| Burst at window edges | Fixed window | GCRA or sliding window |

## Primary sources

- [RFC 6585 section 4: 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html#section-4)
- [RFC 9110 section 10.2.3: Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3)
- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [IETF draft-ietf-httpapi-ratelimit-headers-11](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-ratelimit-headers-11)
- [RFC 9651: Structured Field Values for HTTP](https://www.rfc-editor.org/rfc/rfc9651.html)
- [Redis: Scripting with Lua, replication and TIME](https://redis.io/docs/latest/develop/programmability/eval-intro/)
- [Redis: TIME](https://redis.io/docs/latest/commands/time/)
- [Valkey: Introduction to Eval scripts](https://valkey.io/topics/eval-intro/)
- [redis-py: Lua scripting](https://redis.readthedocs.io/en/stable/lua_scripting.html)
- [redis-py: asyncio examples](https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html)
- [ITU-T I.371: Traffic control and congestion control in B-ISDN (GCRA)](https://www.itu.int/rec/T-REC-I.371)
- [Azure Architecture Center: Rate Limiting pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/rate-limiting-pattern)
- [Uvicorn: Settings, proxy headers](https://uvicorn.dev/settings/)
- [Testcontainers for Python](https://testcontainers-python.readthedocs.io/en/latest/)
