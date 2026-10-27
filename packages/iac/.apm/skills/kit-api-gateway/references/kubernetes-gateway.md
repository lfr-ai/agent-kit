# A Kubernetes Gateway API implementation as the API gateway

Verified as of 2026-10 against the sources listed at the end (Gateway API
v1.6.3 was the latest stable release; v1.7 was in release candidates; Envoy
Gateway v1.9.3 was current). Check release notes and your implementation's
conformance report before using a field.

Ownership: the Gateway API itself (GatewayClass, listeners, TLS and
certificates, release channels, HTTPRoute matching basics, and migration away
from Ingress NGINX) belongs to `kit-edge-networking`. This reference covers
only what changes when a cluster gateway also has to act as an API gateway:
versioned API routes, consumer authentication, and limits. Templates:
[Gateway](../assets/k8s/api-gateway.yaml.template) (the parent a route attaches
to), [HTTPRoute](../assets/k8s/api-httproute.yaml.template), and the Envoy Gateway
[SecurityPolicy](../assets/k8s/security-policy.yaml.template).

## What is portable and what is not

| API gateway need | Gateway API (portable) | Implementation policy (not portable) |
| --- | --- | --- |
| Versioned path, rewrite to the service path | `HTTPRoute` path match + `URLRewrite` (Core/Extended) | |
| Per-route timeouts | `timeouts.request`, `timeouts.backendRequest` (Extended, standard channel) | Finer per-backend timeouts |
| Retries | `retry` is experimental channel only | Usually configured here |
| CORS for browser clients | `CORS` filter (Extended, standard channel) | Some implementations prefer their own |
| Canary or blue-green between service versions | Weighted `backendRefs` (Core) | |
| JWT validation, API keys, OIDC | Not in the API (`ExternalAuth` filter is experimental) | For example Envoy Gateway `SecurityPolicy` |
| Per-consumer rate limits | Not in the API | For example Envoy Gateway `BackendTrafficPolicy` (local or global with a shared rate-limit service) |
| Circuit breaking toward the service | Not in the API | For example `BackendTrafficPolicy` |
| Products, subscriptions, quotas, developer portal | Not in the API | Not usually available; use an API management product |

If you need the last row, put an API management product in front of the
cluster or run its gateway inside the cluster (the API Management self-hosted
gateway is a container that takes configuration from a Developer or Premium
instance). Do not rebuild subscriptions and plans out of route policies.

## API route shape

1. Attach to the platform's HTTPS listener with `parentRefs.sectionName`.
2. Match a versioned prefix (`/orders/v1`) and rewrite to the path the
   service expects. A breaking change is a new route (`orders-v2`) pointing at
   the new service version; both stay until the published sunset date
   (`kit-api-contracts`).
3. Set `timeouts.request` and `timeouts.backendRequest` explicitly;
   `backendRequest` must not exceed `request`, and with retries the whole
   exchange must fit in `request`. Order them below the edge timeout.
4. Allow retries only on idempotent routes, and only when the experimental
   channel is installed deliberately; otherwise configure retries in the
   implementation policy or leave them to clients.
5. Configure CORS with explicit origins in exactly one layer.
6. Do not add headers that the service treats as proof of identity unless the
   service accepts traffic only from the gateway and verifies it
   (see [security and operations](security-and-operations.md)).

## Authentication and limits through policy attachment

- Target policies at the `HTTPRoute` (one API) rather than the whole
  `Gateway`, unless the rule truly applies to every route.
- JWT: list issuer, audiences, and a remote JWKS URI; keep the JWKS cache
  short enough for key rotation. The service still validates tokens and
  authorizes each object (`kit-auth`).
- Rate limits: local limits are per proxy replica, so the effective limit
  scales with replica count; global limits need a shared rate-limit service
  and its store. Key them on a validated claim or client identity, not on a
  header the caller can set.
- These policy APIs were `v1alpha1` at the verification date. Pin the
  implementation release, read its API reference for that release, and test
  the policies in a non-production cluster.
- Watch the policy's status conditions as well as the route's: a policy that
  is not accepted leaves the route unprotected while traffic still flows.

## Sources

- Kubernetes Gateway API concept page:
  <https://kubernetes.io/docs/concepts/services-networking/gateway/>
- Gateway API guides: <https://gateway-api.sigs.k8s.io/guides/>
- Gateway API `HTTPRoute` types at v1.6.3 (timeouts, retry, CORS, filters):
  <https://github.com/kubernetes-sigs/gateway-api/blob/v1.6.3/apis/v1/httproute_types.go>
- Gateway API releases: <https://github.com/kubernetes-sigs/gateway-api/releases>
- Envoy Gateway documentation: <https://gateway.envoyproxy.io/docs/>
- Envoy Gateway API types at v1.9.3 (SecurityPolicy, BackendTrafficPolicy):
  <https://github.com/envoyproxy/gateway/tree/v1.9.3/api/v1alpha1>
- API Management self-hosted gateway:
  <https://learn.microsoft.com/en-us/azure/api-management/self-hosted-gateway-overview>
