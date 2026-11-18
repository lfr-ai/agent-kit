# HTTP middleware

`create_app` always installs request correlation and access logging. Rate
limiting is opt-in. All three are pure ASGI middleware, so they do not buffer
bodies or break streaming responses. Tracing is described in
[telemetry.md](telemetry.md).

## Request correlation

Every HTTP and WebSocket request gets a request ID, and every HTTP response
returns it in `X-Request-ID`, including generic 500 responses.

- The runtime keeps exactly one inbound `X-Request-ID` value when it is 1 to 128
  characters from `A-Z a-z 0-9 . _ : + / = -`. A missing, repeated, oversized
  or malformed value is replaced with a new UUID4 and is never echoed or logged.
- `current_request_id()` returns the ID for the running request and `None`
  outside one. The value lives in a context variable, so tasks started during
  the request inherit it.

```python
from platform_kit_runtime.middleware import current_request_id

request_id = current_request_id()
```

A request ID is a correlation hint that clients control, so do not use it for
authorization, deduplication or idempotency.

## Access logging

The runtime writes one record per HTTP request to the
`platform_kit_runtime.access` logger, with the message `HTTP request completed`
and these `extra` fields:

| Field | Value |
| --- | --- |
| `event` | `runtime.http_request` |
| `http_method` | Request method, or `_OTHER` for nonstandard methods |
| `http_route` | Route template such as `/items/{item_id}`; `None` when no route matched |
| `http_status` | Response status; `500` when the app failed before responding |
| `duration_ms` | Time until the response completed, in milliseconds |
| `request_id` | The correlation ID |

Raw paths, query strings, headers, bodies, client addresses and credentials are
never logged. Health routes log at `DEBUG`, everything else at `INFO`.
Cancelled requests (client disconnects) produce no record. Disable the server's
own access log (for example `uvicorn --no-access-log`) to avoid duplicates that
include raw paths and query strings.

A handled failure (for example a 404 or 429) writes two records on purpose:
`runtime.problem` (`WARNING`, or `ERROR` for 5xx) attributes the failure with
`problem_code`, `instance` (the `urn:uuid` returned in the response body) and
`failure_reason`, while `runtime.http_request` is the access summary every
request gets. Count requests from `runtime.http_request` only; use
`runtime.problem` to find why one failed. A client's `instance` joins the two
records through `request_id`.

## Middleware ownership

| Component | Purpose | Runs where | Default | Platform equivalent? |
| --- | --- | --- | --- | --- |
| Request correlation | `X-Request-ID` on every response and log record | In the app | Always on | No. Ingress does not replace it |
| Access logging | One sanitized record per request with the route template | In the app | Always on | No. Platform request metrics carry no route template or request ID |
| Problem handlers | RFC 9457 error bodies and `runtime.problem` records | In the app | Always on | No |
| `BearerGuard` | Authorization | In the app | Only where an application adds it | No |
| Rate limiting | Per-user, per-tenant or per-client quotas | In the app | Off; opt-in with `APP_RATE_LIMIT` | Partly. IP-based WAF limits and platform request counts are not an app rate limiter |
| Tracing | Server spans | In the app | Off; on with `APP_TRACING` or `APPLICATIONINSIGHTS_CONNECTION_STRING` | No |

Container Apps ingress provides TLS termination, load balancing and platform
request metrics. It does not replace request-ID correlation, sanitized
per-route access records, RFC 9457 problem responses, authorization or
per-user and per-tenant quotas. No middleware is switched by Azure environment
variables; only `APPLICATIONINSIGHTS_CONNECTION_STRING` enables tracing.

## Silent fallbacks

- An invalid or repeated inbound `X-Request-ID` is replaced without a log
  record, so clients cannot generate log noise or inject log content.
- If the rate-limit store fails, the request is let through and the runtime
  logs `runtime.rate_limit_unavailable` at `WARNING`. This fail-open behavior
  is intentional; see [Store failures](#store-failures-fail-open).

`http_route` is the template of the innermost matched route. Routers included
with a `prefix` and mounted apps omit that prefix, for example
`/items/{item_id}` for `/v1/items/1`, because FastAPI exposes no public full
template. With tracing enabled, the server span's `http.route` contains it.

## Correlating every log record

`RequestContextFilter` adds `request_id` and `trace_id` to any record; both are
`None` outside a request or active span. Attach it to handlers, not loggers, so
records from library loggers are covered too:

```python
import logging.config

logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request": {"()": "platform_kit_runtime.middleware.RequestContextFilter"}
        },
        "formatters": {
            "line": {
                "format": "%(levelname)s %(name)s %(message)s "
                "request_id=%(request_id)s trace_id=%(trace_id)s"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "filters": ["request"],
                "formatter": "line",
            }
        },
        "root": {"level": "INFO", "handlers": ["console"]},
    }
)
```

## Middleware order

From outermost to innermost:

1. FastAPI's server span, only when tracing is enabled.
2. Request correlation.
3. Access logging.
4. Starlette's 500 boundary.
5. Middleware the application adds after `create_app`; the last one added
   runs first.
6. Rate limiting, when configured.
7. Exception and problem handlers.
8. The router.

Correlation and access logging sit outside the 500 boundary, so unhandled
errors are logged with their request ID and status. Rate limiting runs after
the application's middleware, so an authentication middleware added after
`create_app` can set the principal it is keyed by.

## Rate limiting

Set a fixed-window policy. Limits apply per client, and health routes and
WebSocket connections are exempt.

```python
from platform_kit_runtime import RuntimeConfig, create_app
from platform_kit_runtime.middleware import RateLimitPolicy

app = create_app(
    config=RuntimeConfig(
        rate_limit=RateLimitPolicy(limit=100, window_seconds=60),
        trusted_proxy_hops=1,
    ),
    probes=(),
)
```

`limit` is 1 to 1,000,000 and `window_seconds` is 1 to 86,400.

### Client keys and proxies

- **Authenticated principal.** If a Starlette `AuthenticationMiddleware`
  (or another middleware) sets an authenticated `BaseUser` in
  `scope["user"]`, the key is its `identity`.
- **Client IP otherwise.** With `trusted_proxy_hops=0` (the default), the key
  is the connection's peer address and `X-Forwarded-For` is ignored. Set it to
  the number of reverse proxies in front of the app that append to
  `X-Forwarded-For`, from 0 to 16. The runtime then uses the entry that the
  client-facing proxy appended and ignores anything the client sent to its
  left. If the header has fewer entries, or that entry is not an IP address,
  the peer address is used.

Behind Container Apps ingress the peer address is the proxy, so with the
default `trusted_proxy_hops=0` every client shares one key. Before enabling
`APP_RATE_LIMIT` there, set `APP_TRUSTED_PROXY_HOPS` to the real number of
proxy hops. `X-Forwarded-For` is honored only when the hop count is above 0 and
the header has at least that many entries. Rate limiting is never switched on
by the platform or by Azure environment variables.
Keys are hashed with SHA-256 before they reach a store, so stores never hold raw
addresses or principals.

### Responses

Requests that are allowed get IETF RateLimit header fields:

```http
RateLimit-Policy: "default";q=100;w=60
RateLimit: "default";r=99;t=60
```

When a client exceeds the limit, the runtime answers before routing with an RFC
9457 problem and logs one `runtime.problem` warning:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 42
Cache-Control: no-store
RateLimit-Policy: "default";q=100;w=60
RateLimit: "default";r=0;t=42

{"type": "about:blank", "title": "Too Many Requests", "status": 429,
 "detail": "The request could not be completed.", "code": "rate_limited",
 "instance": "urn:uuid:..."}
```

### Stores

| Store | Scope | Install |
| --- | --- | --- |
| `InMemoryRateLimitStore` (default) | One process; with N replicas a client may get up to N times the limit | Base |
| `RedisRateLimitStore` | Shared by all replicas; one atomic Lua script per request | `platform-kit-runtime[ratelimit]` |

The in-memory store holds up to 100,000 keys. When it is full, it evicts
expired windows first and then the oldest window. For the Redis store, the
application owns the client and its lifecycle:

```python
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from platform_kit_runtime import RuntimeConfig, create_app
from platform_kit_runtime.middleware import RateLimitPolicy, RedisRateLimitStore

redis = Redis.from_url(os.environ["REDIS_URL"], socket_timeout=0.25)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    yield
    await redis.aclose()


app = create_app(
    config=RuntimeConfig(rate_limit=RateLimitPolicy(limit=100, window_seconds=60)),
    probes=(),
    lifespan=lifespan,
    rate_limit_store=RedisRateLimitStore(client=redis),
)
```

Keep the Redis socket timeout short, because every limited request waits for
the store.

### Store failures: fail open

If the store raises `RateLimitStoreError`, the request proceeds without
RateLimit headers and the runtime logs one `runtime.rate_limit_unavailable`
warning. This is deliberate: an outage of the counter store must not take the
API down. If you need to fail closed, implement the `RateLimitStore` protocol
in the application or enforce the limit at the gateway.

### Limitations

- Fixed windows allow bursts of up to twice the limit across a window boundary.
- Requests that do not match a route still count, and a 429 has no
  `http_route` in its access record.
- Each replica's in-memory store counts separately; use a shared store when the
  combined limit matters.
