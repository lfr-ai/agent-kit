---
name: kit-edge-networking
description: Use when configuring a reverse proxy, load balancer, CDN, TLS, forwarded headers, or streaming edge routes.
license: MIT
---

# Configure and review the edge

The edge decides who reaches the application, over which protocol, with
which client identity, and for how long. Start with the
[review guide](references/guide.md); it also maps when to prefer nginx,
Caddy, Traefik, or a managed Azure edge.

## Procedure

1. Draw the request path (client, CDN or managed edge, load balancer, proxy,
   application server) and record each hop's product, version, and owner.
2. Check TLS per [TLS and certificates](references/tls-and-certificates.md):
   TLS 1.2 minimum and 1.3 preferred, a named Mozilla profile generated for
   the deployed versions, automated ACME or managed renewal with an expiry
   alert, staged HSTS, and stapling only where the certificate has an OCSP URL.
3. Check forwarding per [proxying](references/proxying.md): each hop trusts
   `X-Forwarded-*` or `Forwarded` only from the previous hop, every proxied
   route sends the original scheme and host, and the application server
   restricts trust (for example `uvicorn --proxy-headers
   --forwarded-allow-ips <proxy>`).
4. Make body limits and timeouts explicit at every hop, ordered so the
   innermost component times out first.
5. For WebSocket routes forward upgrade headers; for SSE and other streams
   turn buffering and compression off and keep read timeouts above the
   heartbeat interval.
6. Choose load balancing per [load balancing](references/load-balancing.md):
   layer 4 or 7, the algorithm (power of two choices for many proxy
   replicas, consistent hash only for locality), active and passive health
   checks on readiness with capped outlier ejection, upstream keep-alive
   shorter than the application's, and justified affinity.
7. Align draining with shutdown: the platform grace period covers `preStop`
   plus the application drain, and the balancer stops sending before the
   process stops accepting. Deployment strategies and rollback belong to
   `kit-delivery-pipelines`.
8. Allow proxy retries only for idempotent requests, with bounded attempts,
   backoff, and a retry budget, and only one retrying layer per path; the
   resilience policy is owned by `kit-python-service`.
9. For Kubernetes, follow [Kubernetes ingress](references/kubernetes-ingress.md):
   Gateway API with standard-channel fields, explicit HTTPRoute timeouts,
   cert-manager TLS, and a migration plan off the retired community
   ingress-nginx controller.
10. Configure shared caches per [CDN and proxy caching](references/cdn-and-proxy-caching.md):
    cache only public routes, honor origin `Cache-Control`, never store or
    serve authenticated responses, and prefer versioned asset URLs over
    purges. Application cache semantics belong to `kit-caching`.
11. Review rate and connection limits, security headers, version disclosure,
    and admin exposure per [edge hardening](references/edge-hardening.md).
    Consumer quotas belong to `kit-api-gateway`; per-user and business
    limits belong to `kit-fastapi-service`.
12. Adapt a template instead of writing from memory:
    [nginx](assets/nginx.conf.template), [Caddy](assets/Caddyfile.template),
    [Traefik dynamic config](assets/traefik-dynamic.yaml.template),
    [Envoy](assets/envoy.yaml.template), or Gateway API
    [Gateway](assets/gateway-api/gateway.yaml.template) and
    [HTTPRoute](assets/gateway-api/httproute.yaml.template) (issuer, redirect,
    and gRPC routes are linked from the Kubernetes reference).
13. Validate statically: `nginx -t`, `caddy validate`, `envoy --mode
    validate -c envoy.yaml`, `kubectl apply --dry-run=server`, or a
    non-production Traefik instance, and for nginx run
    [check_nginx_config.py](assets/check_nginx_config.py):

    ```text
    python check_nginx_config.py nginx.conf conf.d/
    ```

    It exits 0 when clean, 1 with findings (`path:line: message`), and 2 for
    unreadable or unparsable input. It checks each file alone and does not
    follow `include`. Besides TLS, disclosure, forwarding, body limits, and
    streaming, it flags upstreams without `keepalive`, cached locations that
    receive credentials without `proxy_no_cache` and `proxy_cache_bypass`
    (mark app-authenticated routes with `# edge:authenticated`), and unused
    `limit_req_zone`/`limit_conn_zone` definitions.
14. Record evidence in the [edge review worksheet](assets/edge-review.md.template)
    and hand reloads and deployments to the named operator; reload
    gracefully, never restart, and keep the previous configuration.

## Acceptance gates

- Only TLS 1.2 and 1.3 are offered, from a named profile; renewal is automated and alerted.
- Forwarded headers are trusted only from known hops; every proxied route forwards the scheme.
- Body limits and timeouts are explicit at every hop.
- Streaming routes are unbuffered and uncompressed; WebSocket upgrades pass every hop.
- Probes hit application readiness; draining is verified and fits inside the grace period.
- The balancing algorithm, health checks, ejection cap, and upstream keep-alive are chosen and recorded.
- Proxy retries cover idempotent requests only, are bounded, and are not stacked across layers.
- Shared caches never store or serve responses to credential-bearing requests.
- Edge rate limits are keyed on the real client address and exempt probes.
- Gateway API resources use standard-channel fields unless an experimental bundle is pinned and recorded.
- The nginx checker (when nginx is used) reports no findings, or each is justified.
- The worksheet is complete and a named operator owns reload and rollback.

## Out of scope

Static checks do not prove runtime behavior. Verify TLS, headers, streaming,
caching, retries, and draining against a non-production deployment before
rollout. API management belongs to `kit-api-gateway`; model gateways belong
to `kit-llm-gateway`.
