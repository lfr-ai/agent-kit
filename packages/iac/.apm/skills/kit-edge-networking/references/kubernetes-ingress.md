# Kubernetes ingress: Gateway API, Ingress, and migration

Verified against the primary sources below on 2026-10-27 (skill baseline
review 2026-10-23). Release-channel facts are as of 2026-10: the latest
stable Gateway API release is v1.6.3 (v1.7.0 is in release candidates).

API-management concerns (consumers, keys, quotas, versions, developer
portal) belong to `kit-api-gateway`. This reference covers plain traffic
routing into a cluster.

## Gateway API resources

| Resource | Owner persona | Purpose | Channel (v1.6.3) |
| --- | --- | --- | --- |
| `GatewayClass` | Infrastructure provider | Names the controller implementation | Standard |
| `Gateway` | Cluster operator | Listeners (port, protocol, hostname, TLS), addresses, which namespaces may attach routes | Standard |
| `HTTPRoute` | Application developer | Host, path, header, and method matches; filters; weighted `backendRefs`; `timeouts` | Standard (since v0.5.0); `timeouts` standard since v1.2.0 |
| `GRPCRoute` | Application developer | gRPC service and method matching | Standard since v1.1.0 |
| `ReferenceGrant` | Target namespace owner | Allows cross-namespace references (for example a route to a Service elsewhere) | Standard |
| `BackendTLSPolicy` | Application admin | TLS from the gateway to the backend (CA, SNI) | Standard |
| `ListenerSet` | Application admin | Listeners attached to a shared Gateway without editing it | Standard |
| `TLSRoute` | Application developer | SNI-based routing of TLS (passthrough or terminate) | Standard |

- HTTPRoute `retry` and `sessionPersistence` are experimental-channel
  fields in v1.6.3; the `main` branch (v1.7 candidates) moves `retry` to
  the standard channel. Install experimental CRDs only when you accept
  breaking changes, and pin the bundle version.
- Policies attach to Gateway API objects through `targetRefs` (policy
  attachment). Implementations add their own policy kinds for features the
  core API lacks, for example Envoy Gateway's `BackendTrafficPolicy`
  (load balancing, retries, circuit breaking, health checks),
  `ClientTrafficPolicy` (client timeouts, connection limits),
  `SecurityPolicy` (authentication, CORS). Treat them as
  implementation-specific: they do not port to another controller.

## Gateway API compared with Ingress

| Concern | Ingress | Gateway API |
| --- | --- | --- |
| Roles | One object, one persona | Separate infrastructure, operator, and developer resources with RBAC per resource |
| Features | Host and path routing, TLS termination | Header, query, and method matching, redirects, rewrites, header modification, mirroring, weighted backends, timeouts, gRPC, TLS passthrough |
| Extensions | Controller-specific annotations | Typed fields, filters, and policy resources |
| Cross-namespace | Not defined | Explicit `allowedRoutes` and `ReferenceGrant` |
| Status | Minimal | Per-parent conditions (`Accepted`, `ResolvedRefs`, `Programmed`) |

The Ingress API remains supported but frozen; new routing features land in
Gateway API.

## ingress-nginx retirement

- Kubernetes SIG Network and the Security Response Committee announced on
  2025-11-11 that the community `kubernetes/ingress-nginx` controller would
  be retired: best-effort maintenance until March 2026, then no releases,
  bug fixes, or security patches. As of 2026-10 the repository is archived
  (read-only). Existing deployments and published images keep working but
  receive no fixes.
- The InGate successor project is also retired.
- This is the community controller only. Vendor controllers with similar
  names (for example NGINX Gateway Fabric) are separate projects with their
  own support status.
- Find it: `kubectl get pods --all-namespaces --selector
  app.kubernetes.io/name=ingress-nginx`.

## Migration approach

1. Inventory every Ingress, IngressClass, and annotation in use
   (snippets, rewrites, rate limits, auth, CORS, timeouts, body size,
   canary, affinity). Annotations are where behavior hides.
2. Choose the target: a conformant Gateway API implementation (check its
   conformance report for the features you need), or another Ingress
   controller if you must stay on Ingress short term.
3. Convert mechanically with `ingress2gateway` (latest v1.2.0), then review
   by hand: annotations without a Gateway API equivalent become
   implementation policies or application changes. Never port
   configuration snippets; they were the security problem.
4. Run both controllers side by side on separate addresses. Compare status
   codes, headers (`X-Forwarded-*`, HSTS), body limits, timeouts, and
   streaming behavior using the [edge review worksheet](../assets/edge-review.md.template).
5. Shift traffic gradually (DNS weights, Front Door origin weights, or a
   weighted upstream), keep the old path warm for rollback, then remove the
   old controller and its admission webhook.

## Envoy-based and other implementations

- Envoy-based data planes: Envoy Gateway, Istio, kgateway, and Cilium's
  layer 7 proxy. Envoy concepts (outlier detection, retry budgets, least
  request) map to their policy resources; see
  [load balancing](load-balancing.md) and the
  [Envoy template](../assets/envoy.yaml.template) for the underlying fields.
- Non-Envoy implementations include NGINX Gateway Fabric and Traefik Proxy.
- On Azure, Application Gateway for Containers implements Gateway API and
  Ingress as a managed regional layer 7 balancer for AKS.

## Timeouts and retries in HTTPRoute

- `timeouts.request`: whole client transaction; `timeouts.backendRequest`:
  one attempt to a backend and must not exceed `request`. `0s` disables a
  timeout; when unspecified the behavior is implementation-specific, so set
  both explicitly.
- Keep the gateway's `request` timeout above the application's own
  deadline so the application fails first with a meaningful error.
- `retry` (experimental in v1.6.3): `codes`, `attempts`, `backoff`. Retry
  only idempotent routes; split write routes into rules without `retry`.
  Without the experimental channel, use the implementation's policy
  resource and keep the semantics from [load balancing](load-balancing.md).
- Streaming routes (SSE, WebSocket, gRPC streams) need `request: 0s` or a
  long timeout, and no retries.

## TLS with cert-manager

- cert-manager (1.15 and later) issues certificates for Gateway listeners
  when the Gateway carries `cert-manager.io/cluster-issuer` (or
  `cert-manager.io/issuer`) and Gateway API support is enabled in its
  configuration (`config.gatewayAPI.enabled=true` with Helm). Install the
  Gateway API CRDs before cert-manager starts, or restart it afterwards.
- A listener is used only when it has a `hostname`, `tls.mode: Terminate`,
  and a `certificateRefs` Secret in the Gateway's namespace.
- ACME HTTP-01 through Gateway API needs a listener on port 80 for the
  challenge; DNS-01 avoids that and supports wildcard names.
- Redirect HTTP to HTTPS with an HTTPRoute `RequestRedirect` filter bound
  to the port 80 listener only, so the HTTPS route never redirects.
- Starting points: [Gateway](../assets/gateway-api/gateway.yaml.template),
  [ClusterIssuer](../assets/gateway-api/cluster-issuer.yaml.template),
  [HTTPRoute](../assets/gateway-api/httproute.yaml.template),
  [HTTPS redirect](../assets/gateway-api/https-redirect.yaml.template), and
  [GRPCRoute](../assets/gateway-api/grpcroute.yaml.template). Each file holds
  one resource; apply the Gateway and issuer before the routes.

## Review checklist

- `allowedRoutes.namespaces` is `Same` or a label `Selector`, never `All`
  on a shared internet-facing Gateway without review.
- Every route's status shows `Accepted=True` and `ResolvedRefs=True` for
  each parent.
- Cross-namespace references have a matching `ReferenceGrant`.
- Timeouts are set on every rule; retries only on idempotent rules.
- The Gateway's forwarded-header and client-address handling is
  documented (load balancer source address preservation or PROXY
  protocol), as in [proxying](proxying.md).
- Experimental-channel fields are listed with the pinned CRD bundle version.

## Primary sources

- <https://kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/>
- <https://kubernetes.io/docs/concepts/services-networking/gateway/>
- <https://gateway-api.sigs.k8s.io/reference/api-types/httproute/>
- <https://gateway-api.sigs.k8s.io/reference/api-types/grpcroute/>
- <https://gateway-api.sigs.k8s.io/geps/gep-1731/>
- <https://gateway-api.sigs.k8s.io/guides/getting-started/migrating-from-ingress/>
- <https://gateway-api.sigs.k8s.io/implementations/>
- <https://github.com/kubernetes-sigs/gateway-api/releases>
- <https://github.com/kubernetes-sigs/ingress2gateway>
- <https://gateway.envoyproxy.io/docs/>
- <https://cert-manager.io/docs/usage/gateway/>
- <https://learn.microsoft.com/azure/application-gateway/for-containers/overview>
