# Proxying: forwarding, limits, streaming, health, and reloads

Reviewed 2026-10-23.

## Forwarded headers and trusted proxies

A proxy replaces the client's TCP connection, so the application sees the
proxy's address and scheme unless the proxy forwards them in headers. Those
headers are plain request headers: any client can send them. Each hop must
trust them only from the hop before it.

| Header | Meaning | Rule |
| --- | --- | --- |
| `X-Forwarded-For` | Client address, then each proxy, comma separated | First trusted hop overwrites or appends; inner hops read the right-most untrusted entry |
| `X-Forwarded-Proto` | Original scheme (`https`) | Set on every proxied route; drives redirects, cookies, and absolute URLs |
| `X-Forwarded-Host` | Original Host header | Set when the upstream receives a different Host |
| `Forwarded` (RFC 7239) | Standard form: `for=`, `proto=`, `host=`, `by=` | Prefer when every hop supports it; do not mix forms on one path |
| PROXY protocol | Client address for layer 4 hops | Enable on both sides or neither |

Configuration per component:

| Component | Trust setting | Client address variable |
| --- | --- | --- |
| nginx | `set_real_ip_from <cidr>`, `real_ip_header X-Forwarded-For`, `real_ip_recursive on` | `$remote_addr` after the realip module |
| Caddy | `servers { trusted_proxies static <cidr> }` | `{client_ip}` |
| Traefik | `entryPoints.<name>.forwardedHeaders.trustedIPs` | Forwarded headers kept only from trusted IPs |
| Uvicorn | `--proxy-headers --forwarded-allow-ips <proxy ip or cidr>` (or `FORWARDED_ALLOW_IPS`) | ASGI `client` and `scheme` |
| Gunicorn | `--forwarded-allow-ips` | WSGI `REMOTE_ADDR`, `wsgi.url_scheme` |

Uvicorn trusts proxy headers only from `127.0.0.1` and `::1` by default. In
containers the proxy is another address, so set the list explicitly; never
use `*` unless the application port is unreachable except through the proxy
and that is enforced by the network.

## Timeouts and body limits

Order timeouts from the outside in: each outer hop waits slightly longer than
the hop inside it, so the innermost component fails first with a useful error
instead of the edge returning a bare 504.

| Setting | nginx | Caddy | Traefik |
| --- | --- | --- | --- |
| Connect to upstream | `proxy_connect_timeout` | `transport http { dial_timeout }` | `serversTransports.forwardingTimeouts.dialTimeout` |
| Wait for response headers | `proxy_read_timeout` (between reads) | `response_header_timeout` | `responseHeaderTimeout` |
| Client body read | `client_body_timeout` | `servers { timeouts { read_body } }` | `entryPoints.<name>.transport.respondingTimeouts.readTimeout` |
| Idle keepalive | `keepalive_timeout` | `timeouts { idle }` | `respondingTimeouts.idleTimeout` |
| Body size | `client_max_body_size` (default 1m) | `request_body { max_size }` | `buffering.maxRequestBodyBytes` |

- Set body limits explicitly per site and raise them only on named upload
  routes; stream large uploads to object storage instead of through the app.
- Keep the application server's keepalive timeout longer than the proxy's
  upstream keepalive, or the proxy reuses connections the app just closed
  (intermittent 502s).

## WebSocket and server-sent events

| Need | nginx | Caddy | Traefik |
| --- | --- | --- | --- |
| Upgrade | `proxy_http_version 1.1`, `Upgrade $http_upgrade`, `Connection $connection_upgrade` | Automatic | Automatic |
| No response buffering | `proxy_buffering off` (or app sends `X-Accel-Buffering: no`) | `flush_interval -1` | `responseForwarding.flushInterval`; no `buffering` middleware |
| No compression | `gzip off` on the route | Keep `encode` off the route | Keep `compress` middleware off the route |
| Long idle | `proxy_read_timeout` above the heartbeat interval | Read and idle timeouts | `respondingTimeouts` and transport idle timeout |

`check_nginx_config.py` treats a location as streaming when its path has a
segment `sse`, `stream`, `streams`, `events`, or `event-stream`, or when the
block contains a `# edge:stream` comment. Mark other streaming routes with
the comment so the check covers them. Heartbeats and reconnect behavior are
covered by the `kit-server-streaming` skill.

## Health checks and readiness-aware load balancing

- Liveness answers "restart me?"; readiness answers "send me traffic?".
  Load balancers must probe readiness through the proxy to the application.
- On shutdown the application fails readiness first, waits for the load
  balancer to notice (probe interval times failure threshold), drains, then
  exits. The platform grace period must cover all of it.
- Open-source nginx only has passive checks (`max_fails`, `fail_timeout`);
  Caddy (`health_uri`), Traefik (`healthCheck`), Front Door, and Application
  Gateway have active probes.
- Probe endpoints are cheap, unauthenticated, rate-limit exempt, excluded
  from access logs and traces, and reveal no internals.
- Algorithms, outlier detection, slow start, draining, and proxy retries
  are covered in [load balancing](load-balancing.md).

## Sticky sessions

| Use | Cost |
| --- | --- |
| Short-term affinity for in-memory caches or WebSocket reconnects | Uneven load; lost state when an instance dies |
| Hiding unshared server-side session state | Deploys and scale-in log users out; avoid |

Prefer shared session storage or stateless tokens. If affinity is needed,
use a cookie set by the balancer with a bounded lifetime, and test instance
loss.

## Zero-downtime reloads

1. Validate: `nginx -t`, `caddy validate`, or Traefik's configuration log.
2. Reload, do not restart: `nginx -s reload` starts new workers and lets old
   ones finish; `caddy reload` swaps config through the admin API; Traefik
   watches its file provider.
3. Keep the previous configuration and reload it to roll back.
4. Long-lived connections stay on old workers until they close; bound their
   lifetime (nginx `worker_shutdown_timeout`) so reloads complete.

## Primary sources

- <https://www.rfc-editor.org/rfc/rfc7239>
- <https://nginx.org/en/docs/http/ngx_http_realip_module.html>
- <https://nginx.org/en/docs/http/ngx_http_proxy_module.html>
- <https://nginx.org/en/docs/http/websocket.html>
- <https://nginx.org/en/docs/control.html>
- <https://caddyserver.com/docs/caddyfile/options>
- <https://caddyserver.com/docs/caddyfile/directives/reverse_proxy>
- <https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/>
- <https://uvicorn.dev/settings/>
- <https://learn.microsoft.com/azure/frontdoor/health-probes>
- <https://learn.microsoft.com/azure/application-gateway/application-gateway-probe-overview>
