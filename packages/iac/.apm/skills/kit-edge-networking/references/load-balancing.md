# Load balancing: algorithms, health, draining, and retries

Verified against the primary sources below on 2026-10-27 (skill baseline
review 2026-10-23). Product and version facts are stated as of 2026-10;
recheck release notes for the versions you deploy.

## Layer 4 or layer 7

| Question | Layer 4 (TCP/UDP) | Layer 7 (HTTP) |
| --- | --- | --- |
| Unit of balancing | Connection | Request (or stream for HTTP/2 and gRPC) |
| Sees | Addresses and ports | Method, path, headers, cookies, status |
| TLS | Passthrough or terminate | Terminates (re-encrypts to the upstream if required) |
| Retries, caching, WAF, header rewrite | No | Yes |
| Client address to the app | PROXY protocol or source address preservation | `X-Forwarded-For` / `Forwarded` |
| Cost | Lowest latency and CPU | Parsing, buffering, certificate management |

- Long-lived HTTP/2 and gRPC connections pin every stream to one backend
  behind a layer 4 balancer. Use a layer 7 hop (or client-side balancing)
  for gRPC, otherwise new instances receive no traffic until clients
  reconnect.
- Put layer 4 in front of a layer 7 tier when you need raw throughput,
  non-HTTP protocols, or static addresses; keep HTTP decisions in one place.

## Algorithms and when each fits

| Algorithm | Picks | Fits | Avoid when |
| --- | --- | --- | --- |
| Weighted round robin | Next backend in turn, respecting weights | Similar instances, short and uniform requests | Request costs vary widely; instances differ in size |
| Least connections / least requests | Backend with the fewest requests in flight | Mixed request durations, long polling, uploads | Very low traffic (no signal); many proxy replicas each see only part of the load |
| Power of two choices | Two random backends, then the less loaded | Large pools, many proxy replicas; avoids every proxy herding onto the same "least loaded" backend | Pools of two or three (degenerates to least-loaded) |
| Consistent hash (ring, rendezvous, Maglev) | Backend owning the hash of a key (client address, URI, header) | Cache locality, sharded or stateful backends; only about 1/n of keys move when a backend changes | Uniform load matters more than locality; hot keys overload one backend |
| Latency-aware (EWMA, least time) | Lowest smoothed response time combined with load | Heterogeneous hardware, noisy neighbors | Few requests per backend; slow routes skew the score; feedback oscillation |

Product mapping:

| Algorithm | nginx | Caddy | Traefik v3.7 | Envoy v3 |
| --- | --- | --- | --- | --- |
| Weighted round robin | Default; `weight=` | `round_robin`, `weighted_round_robin` | `strategy: wrr` (default) | `ROUND_ROBIN` |
| Least connections | `least_conn` | `least_conn` | (use `p2c`) | `LEAST_REQUEST` with `choice_count` set to the pool size |
| Power of two choices | `random two least_conn` | `random_choose 2` | `strategy: p2c` | `LEAST_REQUEST` (default `choice_count: 2`) |
| Consistent hash | `hash $request_uri consistent` (ketama) | `uri_hash`, `header`, `client_ip_hash` (rendezvous hashing) | `strategy: hrw` (client address) | `RING_HASH`, `MAGLEV` with a route `hash_policy` |
| Latency-aware | `least_time` (commercial NGINX Plus only) | none | `strategy: leasttime` | none built in; `LEAST_REQUEST` with `active_request_bias` is the usual substitute |

Caddy's default policy is `random`. Open-source nginx's default is weighted
round robin. Weighted round robin across services (canary splits) is a
different feature: Traefik `weighted` services, Gateway API `backendRefs`
weights, Front Door origin weights.

## Health checks

| Kind | How it works | Strength | Weakness |
| --- | --- | --- | --- |
| Active | The balancer probes each backend on an interval | Detects failure without user traffic; can gate new instances | Probe can pass while real routes fail; probe load grows with proxies times backends |
| Passive | Real responses (errors, timeouts) count against a backend | Reflects real traffic | Needs user traffic to fail first; useless with a single backend |
| Outlier detection | Passive ejection with ejection time, growth on repeat, and a maximum ejected percentage | Removes the one bad instance without emptying the pool | Must cap ejection so a shared failure (database down) does not eject everyone |

Product support:

- nginx open source: passive only (`max_fails`, `fail_timeout`). With a
  single server in a group these are ignored. Active `health_check` and
  `slow_start` are commercial; the `drain` server parameter moved to open
  source in nginx 1.29.6.
- Caddy: active `health_uri`, `health_interval`, `health_fails`,
  `health_passes`; passive `fail_duration`, `max_fails`, `unhealthy_status`,
  `unhealthy_latency`.
- Traefik: active `healthCheck` (path, interval, timeout,
  `unhealthyInterval`) and `passiveHealthCheck` (`failureWindow`,
  `maxFailedAttempts`). A `weighted` service needs `healthCheck: {}` to
  react to unhealthy children.
- Envoy: active `health_checks`, passive `outlier_detection`
  (`consecutive_5xx`, `consecutive_gateway_failure`, `base_ejection_time`,
  `max_ejection_percent`, success-rate and failure-percentage ejection).

Rules:

- Probe readiness, not liveness, and not a static proxy page.
- Require several consecutive failures to eject and several passes to
  return (`unhealthy_threshold` / `healthy_threshold`, `health_fails` /
  `health_passes`) to avoid flapping.
- Cap ejection (`max_ejection_percent` at 50 or less) so a dependency
  outage degrades instead of emptying the pool.
- **Slow start** ramps a recovered or new backend's weight over a window so
  cold caches and JIT warm-up do not take full load at once: Envoy
  `slow_start_config.slow_start_window` (round robin and least request),
  nginx `slow_start` (commercial). Without it, rely on readiness that only
  passes after warm-up.

## Draining and graceful shutdown

The balancer must stop sending new requests before the instance stops
accepting them. Order of events on scale-in or deploy:

1. The platform marks the instance terminating (Kubernetes removes it from
   ready EndpointSlice endpoints; a cloud balancer starts deregistration).
2. The instance keeps serving while every balancer notices: probe interval
   times failure threshold, plus controller propagation.
3. In-flight requests finish within the drain window (nginx `drain`,
   Application Gateway connection draining, Envoy listener draining with
   `--drain-time-s`).
4. The application receives the stop signal, stops accepting, finishes
   in-flight work, and exits before the platform kill deadline.

Kubernetes alignment:

- `terminationGracePeriodSeconds` (default 30 seconds) covers the `preStop`
  hook and the application's own shutdown. If they exceed it, the container
  is killed.
- A short `preStop` sleep (the `sleep` lifecycle action or an exec `sleep`)
  keeps the process serving while endpoint removal propagates to every
  proxy and node.
- Application shutdown timeout < grace period minus `preStop` time; the
  balancer's drain timeout should be at most the application shutdown
  timeout.
- Azure Application Gateway: connection draining is 30 seconds by default
  when not enabled in backend settings, configurable from 1 to 3,600
  seconds; a configuration update ends connections still open after the
  draining timeout.
- Long-lived connections (WebSocket, SSE, gRPC streams) need an explicit
  maximum lifetime or reconnect-on-close in the client, otherwise draining
  waits for the full timeout.

Deployment strategies (rolling, blue-green, canary with weighted traffic)
and their rollback gates belong to `kit-delivery-pipelines`; this skill owns
the balancer settings those strategies rely on.

## Session affinity

| Option | Mechanism | Trade-off |
| --- | --- | --- |
| Balancer cookie | Proxy sets a cookie naming the backend (Caddy `cookie`, Traefik `sticky.cookie`, Application Gateway affinity) | Survives client address changes; uneven load; lost state on instance loss |
| Client address hash | `ip_hash`, `client_ip_hash`, `hrw` | No cookie; many users behind one NAT land on one backend |
| Header or key hash | Consistent hash of a tenant or session header | Good for sharded caches; hot keys |
| None (preferred) | Shared session store or stateless tokens | Even load; deploys and scale-in do not log users out |

Use affinity for performance (warm caches, WebSocket reconnects), never as
the only place state lives. Bound the cookie lifetime and mark it
`Secure; HttpOnly`.

## Upstream connection reuse

- Reuse connections to upstreams: TLS and TCP handshakes per request cost
  latency and CPU and exhaust ephemeral ports.
- nginx: `keepalive N` in the `upstream` block, `proxy_http_version 1.1`,
  and `proxy_set_header Connection ""`. From nginx 1.29.7 an upstream keeps
  up to 32 idle connections per worker and uses HTTP/1.1 by default; set
  both explicitly for older versions and for clarity. `keepalive` limits
  idle connections per worker, not total connections.
- Caddy: `keepalive` (default 2 minutes), `keepalive_idle_conns_per_host`
  (default 32).
- Traefik: `serversTransports.<name>.maxIdleConnsPerHost` and
  `forwardingTimeouts.idleConnTimeout`.
- Envoy: `typed_extension_protocol_options` with
  `common_http_protocol_options.idle_timeout` and
  `max_requests_per_connection`.
- The proxy's upstream idle timeout must be shorter than the application
  server's keep-alive timeout, otherwise the proxy reuses a connection the
  server just closed and returns intermittent 502s.

## Retries at the proxy

Retries multiply load exactly when backends are struggling. The resilience
policy (deadlines, backoff with jitter, idempotency keys, circuit breakers)
is owned by `kit-python-service`; the proxy layer must not contradict it.

| Rule | nginx | Caddy | Traefik | Envoy |
| --- | --- | --- | --- | --- |
| Retry only idempotent requests | Non-idempotent methods are not retried after being sent unless `proxy_next_upstream non_idempotent` | Only `GET` is retried after a sent request unless `lb_retry_match` widens it | `retryNonIdempotentMethod` defaults to `false` | No method filter by default; restrict with `retriable_request_headers` on `:method` |
| Bound attempts and time | `proxy_next_upstream_tries`, `proxy_next_upstream_timeout` | `lb_retries`, `lb_try_duration` | `attempts`, `timeout` | `num_retries`, `per_try_timeout`, route `timeout` |
| Back off | none (next server immediately) | `lb_try_interval` | `initialInterval` | `retry_back_off` |
| Budget across requests | none | none | none | `circuit_breakers.thresholds.retry_budget` |

- Retry on connection failure and refused streams first; retry 502/503/504
  only for idempotent methods and only on another backend.
- Use one retrying layer per hop chain. Retries at the client, the CDN,
  the proxy, and the application multiply (3 x 3 x 3 = 27 attempts).
- Prefer a retry budget (for example 20 percent of active requests with a
  small minimum concurrency) over a fixed count: it caps extra load during
  an outage.
- Gateway API HTTPRoute `retry` is still an experimental-channel field in
  the latest stable release (v1.6.3); see
  [Kubernetes ingress](kubernetes-ingress.md).

## Global and regional load balancing on Azure

As of 2026-10 (Microsoft Learn "Load balancing options"):

| Service | Scope | Layer | Use for |
| --- | --- | --- | --- |
| Azure Front Door (Standard/Premium) | Global | 7 (HTTP/S) | Anycast entry, multi-region failover, caching, WAF, managed certificates |
| Azure Traffic Manager | Global | DNS | Any protocol across regions or hybrid endpoints; failover is limited by DNS caching and TTL |
| Azure Load Balancer | Regional, or global with the cross-region tier | 4 (TCP/UDP) | Non-HTTP traffic, high throughput, static addresses |
| Azure Application Gateway (v2) | Regional | 7 (also TCP/TLS proxy) | WAF, private backends in a virtual network, path routing |
| Application Gateway for Containers | Regional | 7 | Kubernetes traffic via Gateway API or Ingress |

- Application Gateway v1 retired on 2026-04-28; only v2 is supported.
- Azure Front Door (classic) retires on 2027-03-31 and no longer accepts new
  profiles or managed certificates; use Standard or Premium.
- A common shape is Front Door (global) to Application Gateway or a private
  ingress (regional) to the cluster. Every hop has its own probes, timeouts,
  and trusted-proxy list; restrict the origin to Front Door traffic
  (`AzureFrontDoor.Backend` service tag and the `X-Azure-FDID` header).
- API Management also load balances backends, but it is an API gateway,
  owned by `kit-api-gateway`.

## Anti-patterns

- Least-connections across dozens of proxy replicas, each with a partial
  view, sending a herd to the same instance; use power of two choices.
- Health probes that check a dependency (database) on every instance, so
  one shared outage ejects the whole pool.
- `proxy_next_upstream ... non_idempotent` or `retryNonIdempotentMethod:
  true` without application idempotency keys.
- Sticky sessions hiding in-memory session state.
- A grace period shorter than probe detection time plus drain time.

## Primary sources

- <https://nginx.org/en/docs/http/ngx_http_upstream_module.html>
- <https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_next_upstream>
- <https://caddyserver.com/docs/caddyfile/directives/reverse_proxy>
- <https://doc.traefik.io/traefik/reference/routing-configuration/http/load-balancing/service/>
- <https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/retry/>
- <https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/load_balancing/load_balancers>
- <https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/outlier>
- <https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/router_filter>
- <https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination>
- <https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/>
- <https://learn.microsoft.com/azure/architecture/guide/technology-choices/load-balancing-overview>
- <https://learn.microsoft.com/azure/application-gateway/configuration-http-settings>
- <https://learn.microsoft.com/azure/application-gateway/v1-retirement>
- <https://learn.microsoft.com/azure/frontdoor/front-door-caching>
