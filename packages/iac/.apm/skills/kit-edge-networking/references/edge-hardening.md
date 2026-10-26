# Edge hardening: rate limits, headers, and exposure

Reviewed 2026-10-23.

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
- <https://nginx.org/en/docs/http/ngx_http_headers_module.html>
- <https://owasp.org/www-project-secure-headers/>
- <https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html>
- <https://www.rfc-editor.org/rfc/rfc6585#section-4>
- <https://caddyserver.com/docs/api>
- <https://learn.microsoft.com/azure/web-application-firewall/afds/afds-overview>
