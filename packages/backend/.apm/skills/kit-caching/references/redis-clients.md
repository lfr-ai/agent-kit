# Redis-compatible clients and managed services

Verified as of 2026-10-27: redis-py 8.1.0 (released 2026-07-30), Valkey
9.1.3, the Redis licensing page, and the Microsoft Learn retirement FAQ for
Azure Cache for Redis. Re-verify the dated sections before relying on them.

## Own the client in the application lifespan

- Create **one** asynchronous client per process in the composition root or
  the framework lifespan; inject it (or the cache adapter wrapping it) into
  collaborators. Never create a client at import time or per request.
- The client owns an internal connection pool. Close it on shutdown with
  `await client.aclose()`; asyncio clients have no destructor that does it
  for you.
- A pool belongs to the event loop that created it. Test suites that create
  a new loop per test must also create the client per test (a fixture), or
  connections fail with loop errors.
- If several clients share one `ConnectionPool`, pass `connection_pool=` and
  close the pool explicitly; `Redis.from_pool(pool)` hands ownership of the
  pool to a single client.

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shop.cache.redis_cache import RedisCache, create_redis_client
from shop.cache.settings import CacheSettings


def build_lifespan(settings: CacheSettings):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = create_redis_client(settings)
        app.state.cache = RedisCache(
            client, operation_timeout_seconds=settings.operation_timeout_seconds
        )
        try:
            yield
        finally:
            await client.aclose()

    return lifespan
```

The full adapter and factory are in
[redis_cache.py.template](../assets/redis_cache.py.template). Wire the
lifespan into the app factory per `kit-fastapi-service`.

## Configure the connection for a cache

| Parameter (redis-py asyncio) | Recommendation for an optional cache | Notes |
| --- | --- | --- |
| URL scheme | `rediss://` outside local development | `redis://` is plain TCP |
| `socket_connect_timeout` | Hundreds of milliseconds | Library default is 10 seconds |
| `socket_timeout` | Tens of milliseconds to low hundreds | Library default is 10 seconds; per command |
| `retry` | `Retry(ExponentialWithJitterBackoff(cap=..., base=...), 1)` from `redis.asyncio.retry` | Default since redis-py 6.0 is 3 retries with jittered exponential backoff |
| `max_connections` | Set explicitly from the worker's concurrency | Bounded pool protects the server |
| `health_check_interval` | A few seconds when traffic is bursty | Integer seconds; idle connections send `PING` before reuse |
| `client_name` | Service name | Visible in `CLIENT LIST` |
| `decode_responses` | `False` | The cache port stores bytes |
| `protocol` | Leave default or set `3` explicitly | redis-py 8.0+ speaks RESP3 on the wire by default while keeping RESP2-shaped Python responses |

Also bound the whole operation, including retries, with `asyncio.timeout`
in the adapter so the cache never consumes more than its budget of the
request deadline. Map `redis.exceptions.RedisError`, `TimeoutError`, and
`OSError` to one `CacheUnavailableError`.

The synchronous client uses `redis.retry.Retry`; the asynchronous client
needs `redis.asyncio.retry.Retry` because its retry loop awaits.

## TLS and authentication

- Use TLS with certificate verification (`ssl_cert_reqs` defaults to
  `"required"` and hostname checking is on). Provide `ssl_ca_certs` when the
  server uses a private CA; never disable verification to "make it work".
- Authenticate as a dedicated ACL user (`username` plus `password`) limited
  to the service's key prefix and command categories; see
  [distributed.md](distributed.md#secure-the-store).
- Token-based authentication (for example Microsoft Entra ID with Azure
  Managed Redis) uses a credential provider that refreshes the token and
  re-authenticates live connections; follow the vendor's redis-py sample
  rather than passing a static token as a password.
- Load URLs and secrets through the settings facet
  ([settings template](../assets/cache_settings.py.template), `kit-config`);
  never log the URL, which may contain the password.

## Client-side caching (server-assisted)

Redis client-side caching keeps results of read commands in the client and
relies on the server's `CLIENT TRACKING` invalidation messages over RESP3.
In redis-py it is enabled with `cache_config=CacheConfig()` and, per its
documentation, is available **only for synchronous clients** (standalone,
Cluster, Sentinel). Asyncio services therefore implement their own L1 with
short TTLs (see [in-process.md](in-process.md)) or broadcast invalidation.
When it is available, it suits read-mostly keys with modest cardinality;
size the local cache and monitor its memory.

## Topologies

| Topology | Client | Consider |
| --- | --- | --- |
| Standalone (one primary, optional replicas) | `redis.asyncio.Redis` | Simplest; replicas are for availability, not read scaling, unless reads tolerate lag |
| Sentinel | `redis.asyncio.sentinel.Sentinel(...).master_for(...)` | Failover discovery; client reconnects to the new primary |
| Cluster (hash slots across shards) | `redis.asyncio.cluster.RedisCluster` | Multi-key commands and scripts must stay within one slot; use hash tags deliberately |

Managed services may present a cluster behind one endpoint or expose the
cluster protocol; check the service's cluster policy and use the matching
client. Retry settings in cluster mode differ (cluster-specific errors are
always retried); read the redis-py clustering and retry pages before tuning.

## Valkey compatibility

Valkey is a BSD-3-Clause fork created from the open source Redis project
just before the 2024 license change. It speaks the same protocol, and
redis-py works with it for the commands this skill uses (`GET`, `SET` with
`NX`/`PX`, `MGET`, `UNLINK`, `EVAL`/`EVALSHA`, `PUBLISH`, `SCAN`, `INFO`).
Both projects add features independently after the fork, so:

- Keep the cache adapter to the core command set above.
- Run the contract tests ([testing.md](testing.md)) against the server you
  deploy, not only against the other one.
- Valkey also maintains its own client libraries (for example Valkey GLIDE);
  switching clients is an adapter change behind the cache port.

## Licensing (dated facts, verified 2026-10-27)

| Server version | License |
| --- | --- |
| Redis 7.2 and earlier | BSD-3-Clause |
| Redis Community Edition 7.4.x to 7.8.x | Dual RSALv2 or SSPLv1 (changed March 2024) |
| Redis Open Source 8 and later | Tri-license: RSALv2, SSPLv1, or AGPLv3 (OSI-approved) |
| Valkey | BSD-3-Clause |
| redis-py client | MIT (client license is separate from the server license) |

RSALv2 restricts offering the software as a managed service to third
parties; SSPLv1 and AGPLv3 are copyleft with network-use obligations. Using
a server unmodified inside your own deployment is usually unaffected, but
license decisions belong to the consumer's legal review, not to this skill.
Record the chosen server and license in the project's dependency notes.

## Azure managed options (dated facts, verified 2026-10-27 on Microsoft Learn)

- **Azure Cache for Redis** Basic, Standard, and Premium tiers retire on
  2028-09-30; remaining instances are disabled from 2028-10-01.
- **Azure Cache for Redis** Enterprise and Enterprise Flash tiers retire on
  2027-03-31; remaining instances are disabled from 2027-04-01.
- Microsoft recommends migrating to **Azure Managed Redis**, which is built
  on Redis Enterprise software, is clustered by default (OSS cluster policy
  by default, non-clustered option up to 25 GB), zone redundant by default,
  and uses Microsoft Entra ID authentication by default.
- New designs on Azure should therefore target Azure Managed Redis and use
  a cluster-aware client unless a non-clustered instance is chosen.
  Provisioning, networking, and policy belong to the infrastructure skills;
  this skill only fixes the client contract.

Other clouds offer Redis- or Valkey-compatible managed services; verify
their engine, version, license, and cluster mode in current vendor
documentation before choosing.

## Sources

- redis-py asyncio examples:
  <https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html>
- redis-py retry helpers: <https://redis.readthedocs.io/en/stable/retry.html>
- redis-py backoff: <https://redis.readthedocs.io/en/stable/backoff.html>
- redis-py RESP3 features and client-side caching:
  <https://redis.readthedocs.io/en/stable/resp3_features.html>
- redis-py connections: <https://redis.readthedocs.io/en/stable/connections.html>
- redis-py clustering: <https://redis.readthedocs.io/en/stable/clustering.html>
- redis-py exceptions: <https://redis.readthedocs.io/en/stable/exceptions.html>
- Redis, redis-py production usage:
  <https://redis.io/docs/latest/develop/clients/redis-py/produsage/>
- Redis client-side caching reference:
  <https://redis.io/docs/latest/develop/reference/client-side-caching/>
- Redis `CLIENT TRACKING`: <https://redis.io/docs/latest/commands/client-tracking/>
- Redis TLS: <https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/>
- Redis licenses: <https://redis.io/legal/licenses/>
- Valkey repository and license: <https://github.com/valkey-io/valkey>
- Valkey clients: <https://valkey.io/topics/clients/>
- Microsoft Learn, Azure Cache for Redis retirement FAQ:
  <https://learn.microsoft.com/azure/azure-cache-for-redis/retirement-faq>
- Microsoft Learn, Azure Managed Redis overview:
  <https://learn.microsoft.com/azure/redis/overview>
- Microsoft Learn, Microsoft Entra ID authentication for Azure Managed Redis:
  <https://learn.microsoft.com/azure/redis/entra-for-authentication>
