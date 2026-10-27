# Edge networking review guide

Reviewed 2026-10-23. Version-sensitive values (TLS profiles, defaults, flags)
come from the primary sources at the end; recheck them for the versions you
deploy.

## Reference map

| Concern | Reference |
| --- | --- |
| Protocols, ciphers, certificates, ACME, HSTS, revocation | [TLS and certificates](tls-and-certificates.md) |
| Forwarded headers, trusted proxies, timeouts, body limits, WebSocket, SSE, health routing, sticky sessions, reloads | [Proxying](proxying.md) |
| Rate limiting, security headers, disclosure, admin surfaces | [Edge hardening](edge-hardening.md) |
| Layer 4 or 7, algorithms, health checks, outlier detection, draining, affinity, upstream keep-alive, proxy retries, Azure global and regional balancers | [Load balancing](load-balancing.md) |
| Gateway API, Ingress, ingress-nginx retirement and migration, HTTPRoute timeouts and retries, cert-manager | [Kubernetes ingress](kubernetes-ingress.md) |
| Proxy and CDN caches, authenticated responses, purge and cache busting | [CDN and proxy caching](cdn-and-proxy-caching.md) |

Streaming-specific application behavior (heartbeats, reconnects, event IDs)
belongs to the `kit-server-streaming` skill; container runtime settings
belong to `kit-containers`; deployment review belongs to `kit-infra-review`;
deployment strategies belong to `kit-delivery-pipelines`; API management
belongs to `kit-api-gateway`; application caching semantics belong to
`kit-caching`.

## Choose the edge component

| Situation | Prefer | Why | Watch for |
| --- | --- | --- | --- |
| Single host or small fleet, team knows nginx | nginx | Mature, explicit, cheap | Inheritance rules for `proxy_set_header` and `add_header`; no active health checks in open source |
| Small fleet, want automatic certificates with little config | Caddy | ACME, redirects, forwarded headers, and stapling on by default | Defaults hide behavior; pin the version and read release notes |
| Containers with dynamic discovery (labels, Kubernetes) | Traefik | Routes follow service discovery | Middleware order and buffering; static versus dynamic config split |
| Global users, DDoS and WAF needs, multiple regions on Azure | Azure Front Door | Anycast edge, managed certificates, WAF, health-based origin routing | Origin must accept only Front Door (check `X-Azure-FDID` and service tag) |
| Regional Azure application behind a virtual network | Azure Application Gateway | Layer 7 load balancing, WAF, private backends | Probe paths, request timeout, body size limits per SKU |
| Plain TCP or TLS passthrough | Layer 4 load balancer | Lowest overhead | No HTTP headers; use PROXY protocol for client address |
| Service-to-service or advanced traffic policy (outlier detection, retry budgets) | Envoy, directly or through an Envoy-based Gateway API implementation | Richest balancing and resilience controls | Large configuration surface; validate with `envoy --mode validate` |
| Kubernetes cluster ingress | A conformant Gateway API implementation | Role-separated, portable routing | Experimental-channel fields; community ingress-nginx is retired |

A managed edge in front of a self-managed proxy is common; review every hop,
because each hop has its own timeouts, limits, and trusted-proxy list.

## Quality gates

- Only TLS 1.2 and 1.3 are offered; the profile matches a named Mozilla
  configuration for the deployed versions.
- Certificates renew automatically and expiry is alerted.
- Each hop trusts forwarded headers only from the previous hop.
- Every proxied route forwards the original scheme and host.
- Body limits and timeouts are explicit at every hop and ordered so the
  innermost component times out first.
- Streaming routes disable buffering and compression; WebSocket routes pass
  upgrade headers.
- Load balancers route on application readiness.
- Configuration is tested before a graceful reload; the previous version is
  kept for rollback.

## Failure modes

| Symptom | Likely cause |
| --- | --- |
| Redirect loop between HTTP and HTTPS | App does not trust `X-Forwarded-Proto`, sees HTTP, redirects again |
| Logged client IP is always the load balancer | Real-IP handling missing or trusted list wrong |
| Rate limits apply to all users at once | Limit keyed on the proxy address instead of the client |
| Any client can spoof its IP | `--forwarded-allow-ips '*'` or `real_ip_from 0.0.0.0/0` |
| Server-sent events arrive in bursts at the end | Proxy buffering or compression on the stream route |
| WebSocket closes after about a minute | Idle timeout on one hop shorter than the heartbeat |
| 413 errors on uploads after a proxy change | Body limit default (1 MiB in nginx) applied silently |
| 502 bursts during deploys | Instances stopped before leaving rotation; no readiness drain |
| Headers vanish on one route | A location-level `add_header` or `proxy_set_header` replaced the inherited list |
| Site unreachable for months after a mistake | HSTS preload or long max-age on a host that cannot serve HTTPS |
| Intermittent 502s on idle upstream connections | Proxy upstream keep-alive outlives the application server's keep-alive |
| One user sees another user's page | Shared cache stored a response to an authenticated request |
| Outage amplified during an incident | Retries stacked at several layers, or retries of non-idempotent requests |
| All instances ejected at once | Outlier detection without a maximum ejection percentage |

## Anti-patterns

- `Strict-Transport-Security` with `preload` on the first rollout.
- Copying a cipher list from an old blog post instead of the generator.
- Trusting `X-Forwarded-For` from everywhere "because we are behind a load balancer".
- Health checks that hit a static proxy page, so dead applications stay in rotation.
- Sticky sessions used to hide server-side session state that should be shared.
- Restarting the proxy instead of reloading, dropping every open connection.

## Verification

1. Static: `nginx -t`, `caddy validate`, or a Traefik dry run in a non-production
   instance; `python check_nginx_config.py <files>` for nginx.
2. TLS: `openssl s_client -connect host:443 -tls1_1` must fail;
   `-tls1_2` and `-tls1_3` must succeed; inspect the chain and expiry.
3. Headers: `curl -sSI https://host/` shows HSTS, nosniff, and no version.
4. Forwarding: in a test environment, send a spoofed `X-Forwarded-For`
   and confirm the application logs the real client address.
5. Streaming: the first event arrives before the producer finishes; a
   WebSocket stays open longer than every idle timeout.
6. Health: mark an instance unready and confirm it leaves rotation before it stops.
7. Record results in the [edge review worksheet](../assets/edge-review.md.template).

## Primary sources

- <https://ssl-config.mozilla.org/>
- <https://nginx.org/en/docs/http/ngx_http_proxy_module.html>
- <https://caddyserver.com/docs/caddyfile/directives/reverse_proxy>
- <https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/>
- <https://learn.microsoft.com/azure/frontdoor/front-door-overview>
- <https://learn.microsoft.com/azure/application-gateway/overview>
- <https://www.rfc-editor.org/rfc/rfc7239>
- <https://uvicorn.dev/settings/>
