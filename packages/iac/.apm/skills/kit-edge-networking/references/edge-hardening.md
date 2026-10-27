# Edge hardening: rate limits, headers, and exposure

Reviewed 2026-10-23; rate limiting section extended and re-verified
2026-10-27 (product facts as of 2026-10).

## Rate limiting: edge or application

| Limit | Where | Key | Why |
| --- | --- | --- | --- |
| Connection and request floods | Edge or managed WAF | Client address | Cheapest place to drop traffic |
| Login and password reset attempts | Application, optionally also edge | Account and client address | Only the app knows the account |
| Per-user or per-tenant quotas | Application | Authenticated identity | Edge cannot see identity reliably |
| Expensive endpoints (search, export) | Application, with an edge ceiling | Identity and route | App knows cost; edge caps abuse |

- Key edge limits on the real client address (after trusted-proxy handling),
  otherwise every user shares the load balancer's bucket.
- Return 429 with `Retry-After`; exempt health probes.
- Use a burst allowance so normal page loads with many parallel requests pass.
- With several proxy replicas, local counters multiply the effective limit;
  accept that or use a shared store or the managed edge.

### Layering

| Layer | Purpose | Owner |
| --- | --- | --- |
| Managed edge WAF (Front Door, Application Gateway) | Volumetric and per-address floods before they reach your network | This skill |
| Reverse proxy (`limit_req`, `limit_conn`, `rateLimit`) | Per-address ceilings and concurrency caps per route | This skill |
| API gateway | Per-consumer quotas, subscription tiers, key-based throttling | `kit-api-gateway` |
| Application | Per-user, per-tenant, and business limits (login attempts, exports) with a shared counter store | `kit-fastapi-service` |

Edge limits are coarse safety nets set well above legitimate peaks; they
must never be the only control for business rules.

### nginx: `limit_req` and `limit_conn`

```nginx
# http context
limit_req_zone  $binary_remote_addr zone=per_client:10m rate=20r/s;
limit_req_zone  $binary_remote_addr zone=login:1m rate=10r/m;
limit_conn_zone $binary_remote_addr zone=conn_per_client:10m;
limit_req_status  429;
limit_conn_status 429;

# server or location context
limit_req  zone=per_client burst=40 nodelay;  # absorb page-load bursts, reject beyond
limit_conn conn_per_client 50;

location = /login {
    limit_req zone=login burst=5;             # queue a few, then reject
}
```

- `limit_req` is a leaky bucket. Without `burst`, any request faster than
  the rate is rejected. `burst` queues excess requests and releases them at
  the rate; `nodelay` serves the burst immediately while still counting
  it; `delay=N` (1.15.7) serves the first N excess requests without delay
  and delays the rest.
- `limit_req` directives are inherited only when the current level defines
  none, like `proxy_set_header`; repeat the general zone in a location that
  adds its own.
- Zone sizing: a state is 64 bytes on 32-bit and 128 bytes on 64-bit
  platforms, so 1 MB holds about 8,000 client states on 64-bit; `10m`
  tracks about 80,000 addresses. When the zone is full the least recently
  used state is evicted, and if none can be freed the request is rejected.
- `$binary_remote_addr` (4 or 16 bytes) is the key; requests with an empty
  key are not limited, which allows exemptions via a `map` that sets the
  key to `""` for probes or trusted networks.
- `limit_conn` counts connections that have a request in progress; with
  HTTP/2 and HTTP/3 each concurrent request counts as a connection.
- Roll out with `limit_req_dry_run on` and the `$limit_req_status`
  variable in the access log, then enforce.
- nginx does not add `Retry-After` to 429 responses; add it with
  `add_header Retry-After <seconds> always` in a named error location if
  clients need it.
- [check_nginx_config.py](../assets/check_nginx_config.py) reports a
  `limit_req_zone` or `limit_conn_zone` that no directive in the file uses.

### Caddy

Caddy (v2.11) has no rate limiter in the standard distribution. The
`rate_limit` handler from the third-party `github.com/mholt/caddy-ratelimit`
module (not an official Caddy project) must be compiled in with `xcaddy`.
It uses a sliding window per zone, keys zones on placeholders such as
`{remote_host}`, sets `Retry-After`, and can share state across instances
through Caddy storage. Pin the module version and treat it as a
dependency to review. Without it, put the limit in a managed edge or the
application.

### Traefik

The `rateLimit` middleware (Traefik v3.7) uses `average` requests per
`period` with a `burst` (default 1). `sourceCriterion` selects the key:
the immediate peer address by default (the load balancer's address when one
is in front), `ipStrategy.depth` or `excludedIPs` to pick the right
`X-Forwarded-For` entry behind trusted proxies, or
`requestHeaderName` / `requestHost`. Counters are per Traefik instance
unless the optional `redis` block shares them across instances. The
separately documented "distributed rate limit" middleware is a Traefik Hub
feature, not part of Traefik Proxy. `inFlightReq` caps concurrent requests,
the analogue of `limit_conn`; its default `sourceCriterion` is the request
host (one cap for the whole site), so set `ipStrategy` for a per-client cap.

### Azure WAF rate limit rules

| Setting | Front Door WAF | Application Gateway WAF v2 |
| --- | --- | --- |
| Rule type | Custom rule, type rate limit | Custom rule, type rate limit (latest WAF engine required) |
| Window | Fixed window of 1 or 5 minutes | Sliding window of 1 or 5 minutes |
| Grouping | Client socket address by default (may be a proxy); on Premium also country/region, ASN, or JA4 fingerprint (some in preview), or none | `ClientAddr` (default), `GeoLocation`, `None`, `ClientAddrXFFHeader`, `GeoLocationXFFHeader` |
| Accuracy | Approximate; larger windows and thresholds are more accurate | Approximate; each gateway instance counts separately |

- Combine a match condition (path, method, header) with the threshold, for
  example a strict rule on `/login` and a loose rule on everything.
- Group on `X-Forwarded-For` only when the previous hop is trusted and
  overwrites the header; otherwise clients choose their own bucket.
- Start in log or detection mode, review the logs, then block.

## Security headers

Set baseline headers at the edge only when the application does not; one
owner per header avoids duplicates and conflicts.

| Header | Value | Owner |
| --- | --- | --- |
| `Strict-Transport-Security` | Staged `max-age` (see TLS reference) | Edge |
| `X-Content-Type-Options` | `nosniff` | Edge or app |
| `Referrer-Policy` | `strict-origin-when-cross-origin` or stricter | Edge or app |
| `X-Frame-Options` / CSP `frame-ancestors` | `DENY` or `'none'` unless framing is required | App preferred |
| `Content-Security-Policy` | Application specific | App |
| `Permissions-Policy` | Disable unused features | App |
| `Server`, `X-Powered-By` | Removed or generic | Edge |

nginx drops inherited `add_header` lines in any block that adds its own;
repeat the full set or use an include file. Use `always` so errors carry them.

## Exposure

- Admin APIs (Caddy admin, Traefik dashboard and API, nginx `stub_status`)
  listen on localhost or a private network only, with authentication.
- Metrics endpoints are scraped over a private network, never published.
- Unknown host names are rejected rather than served by the first site.
- Error pages do not reveal versions, upstream addresses, or stack traces.
- Directory listing is off; only intended paths are routed.

## Anti-patterns

- Rate limiting keyed on `$http_x_forwarded_for` (client controlled).
- A WAF in detection mode forever, never reviewed.
- Copying a full CSP into the proxy for every application.
- Exposing the Traefik dashboard with `api.insecure: true`.

## Primary sources

- <https://nginx.org/en/docs/http/ngx_http_limit_req_module.html>
- <https://nginx.org/en/docs/http/ngx_http_limit_conn_module.html>
- <https://github.com/mholt/caddy-ratelimit>
- <https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/ratelimit/>
- <https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/inflightreq/>
- <https://learn.microsoft.com/azure/web-application-firewall/afds/waf-front-door-rate-limit>
- <https://learn.microsoft.com/azure/web-application-firewall/ag/rate-limiting-overview>
- <https://nginx.org/en/docs/http/ngx_http_headers_module.html>
- <https://owasp.org/www-project-secure-headers/>
- <https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html>
- <https://www.rfc-editor.org/rfc/rfc6585#section-4>
- <https://caddyserver.com/docs/api>
- <https://learn.microsoft.com/azure/web-application-firewall/afds/afds-overview>
