---
name: kit-edge-networking
description: Use when adding or reviewing a reverse proxy, load balancer, TLS, forwarded headers, or WebSocket/SSE edge routing.
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
6. Route load balancer probes to application readiness, confirm draining on
   shutdown, and justify any sticky sessions.
7. Review rate limits, security headers, version disclosure, and admin
   exposure per [edge hardening](references/edge-hardening.md).
8. Adapt a template instead of writing from memory:
   [nginx](assets/nginx.conf.template), [Caddy](assets/Caddyfile.template),
   or [Traefik dynamic config](assets/traefik-dynamic.yaml.template).
9. Validate statically: `nginx -t`, `caddy validate`, or a non-production
   Traefik instance, and for nginx run
   [check_nginx_config.py](assets/check_nginx_config.py):

   ```text
   python check_nginx_config.py nginx.conf conf.d/
   ```

   It exits 0 when clean, 1 with findings (`path:line: message`), and 2 for
   unreadable or unparsable input. It checks each file alone and does not
   follow `include`.
10. Record evidence in the [edge review worksheet](assets/edge-review.md.template)
    and hand reloads and deployments to the named operator; reload
    gracefully, never restart, and keep the previous configuration.

## Acceptance gates

- Only TLS 1.2 and 1.3 are offered, from a named profile; renewal is automated and alerted.
- Forwarded headers are trusted only from known hops; every proxied route forwards the scheme.
- Body limits and timeouts are explicit at every hop.
- Streaming routes are unbuffered and uncompressed; WebSocket upgrades pass every hop.
- Probes hit application readiness; draining is verified.
- The nginx checker (when nginx is used) reports no findings, or each is justified.
- The worksheet is complete and a named operator owns reload and rollback.

## Out of scope

Static checks do not prove runtime behavior. Verify TLS, headers, streaming,
and draining against a non-production deployment before rollout.
