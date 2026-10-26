---
description: Apply to reverse proxy and edge configuration for nginx, Caddy, and Traefik.
applyTo: "**/nginx/**,**/nginx*.conf,**/nginx*.conf.template,**/Caddyfile,**/*.caddy,**/traefik/**,**/traefik*.yml,**/traefik*.yaml"
---

- Offer only TLS 1.2 and 1.3 from a named Mozilla profile generated for the deployed versions.
- Trust forwarded client-address and scheme headers only from the known previous hop; never trust all sources.
- Forward the original scheme and host on every proxied route; in nginx a level that sets any `proxy_set_header` or `add_header` replaces the inherited list.
- Set request body limits and upstream timeouts explicitly instead of relying on defaults.
- Disable response buffering and compression on streaming routes and forward upgrade headers on WebSocket routes.
- Route load balancer probes to application readiness, not to a static proxy page.
- Hide server versions and keep admin and metrics endpoints off public listeners.
- Validate configuration before a graceful reload; do not restart or reload production from an authoring session.
- Use the `kit-edge-networking` skill for procedures and templates.
