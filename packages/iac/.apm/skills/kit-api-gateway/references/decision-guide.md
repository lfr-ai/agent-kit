# Decide whether and which API gateway to use

Verified as of 2026-10 against the sources listed at the end. Product tiers,
feature matrices, and project status change; re-check them before you commit
to a design and record the check date in the
[review worksheet](../assets/gateway-review.md.template).

## Start with "do we need one at all?"

A gateway is another network hop, another failure domain, another bill, and
another place where policy can drift from code. Add one only when at least one
of these is a real, current need:

| Need | Why a gateway helps | Cheaper alternative when the need is small |
| --- | --- | --- |
| Many external consumers with their own keys, plans, and quotas | Products, subscriptions, per-consumer counters, self-service onboarding | Issue OAuth clients and limit in the service |
| Several services behind one public host and versioned paths | Central routing, version sets, uniform errors | A reverse proxy route table (`kit-edge-networking`) |
| One security baseline across teams (token validation, IP rules, size limits) | Policy at global scope that every API inherits | Shared middleware library in each service |
| A developer portal and published contracts for partners | Generated portal, try-it console, onboarding flow | Static docs from the OpenAPI file (`kit-api-contracts`) |
| Protocol mediation (SOAP to REST, header/claim mapping, legacy auth) | Transformation policies without touching the legacy system | An adapter service |
| Shared spend control for model APIs | Token limits and token metrics per consumer | A model gateway (`kit-llm-gateway`) |

If the honest answer is "one internal service and one client", skip the
gateway: put TLS, body limits, and timeouts at the edge
(`kit-edge-networking`) and authentication, rate limiting, and errors in the
service (`kit-auth`, `kit-fastapi-service`). Revisit when a second consumer
or team appears.

## Split responsibilities by layer

Decide ownership per concern before writing any policy. Duplicating a check in
two layers is fine when it is defense in depth; owning it nowhere is the
failure to avoid.

| Concern | Edge (CDN, WAF, load balancer, reverse proxy) | API gateway | Service |
| --- | --- | --- | --- |
| TLS termination, certificates, HTTP/2, HSTS | Owns | Re-terminates or passes through | Trusts forwarded scheme from known hop |
| WAF rules, bot and volumetric DDoS protection | Owns | No | No |
| Connection and request-rate floods per IP | Owns (coarse) | Optional backstop | No |
| Consumer identity: keys, subscriptions, products | No | Owns | Sees a consumer id header at most |
| Token validation (issuer, audience, expiry, signature) | No | Coarse gate | Owns the authoritative check |
| Object-level authorization ("may user X read order 42") | No | Never | Owns |
| Per-consumer rate limits and quotas | No | Owns | Owns limits tied to business state |
| Request shape validation against the contract | No | Optional coarse gate | Owns |
| Error format (`application/problem+json`) | Pass through | For gateway-generated errors | For application errors |
| Caching of public, cacheable responses | CDN | Optional | Emits `Cache-Control`/`ETag` |
| Retries and circuit breaking toward the service | No | Circuit breaker on backend | Owns retries to its own dependencies |
| Model-specific routing, fallbacks, prompt policy | No | Token limits only | `kit-llm-gateway` |

Concept owners in this toolkit: the edge is `kit-edge-networking`, the HTTP
contract and its compatibility rules are `kit-api-contracts`, token
validation in the service is `kit-auth`, application middleware and in-app
rate limiting are `kit-fastapi-service`, and model gateways are
`kit-llm-gateway`. Refer to those skills instead of re-deciding their rules
here.

## Options

### Azure API Management

A managed gateway, management plane, and developer portal. Choose the tier
from the official feature matrix, not from memory; at the verification date the
matrix lists:

| Tier family | Tiers | Notes from the feature matrix |
| --- | --- | --- |
| Consumption | Consumption | Serverless billing, automatic scale; no `rate-limit-by-key` or `quota-by-key`, no VNet, no developer portal, no self-hosted gateway |
| Classic | Developer, Basic, Standard, Premium | Developer has no SLA and is for non-production; Premium adds multi-region, availability zones, VNet injection, and the self-hosted gateway |
| v2 | Basic v2, Standard v2, Premium v2 | All have an SLA and support workspaces; Standard v2 and Premium v2 reach backends in a VNet and accept private endpoints; Premium v2 adds VNet injection and zones |

Facts that change designs (check them again):

- v2 tiers need management API version `2024-05-01` or later and cannot be
  upgraded in place from classic tiers; a move to v2 is a new instance.
- v2 tiers currently lack multi-region deployment, backup and restore, and the
  self-hosted gateway. Plan disaster recovery as redeploy-from-Git plus a
  second instance, not as restore.
- The self-hosted gateway is a container you run (for example on Kubernetes)
  that pulls configuration from an instance in the Developer or Premium tier.
  Use it when APIs must be served close to on-premises or other-cloud
  backends; you then own its patching, scale, and certificates.
- Workspaces let separate teams own their APIs, products, and policies inside
  one instance, optionally on a dedicated workspace gateway. They are a
  delegation boundary, not an environment boundary.

### Kubernetes Gateway API implementations

For clusters, the Gateway API (`gateway.networking.k8s.io`) is the portable
routing layer. A platform team owns `GatewayClass` and `Gateway`; application
teams own `HTTPRoute`. Core and Extended features (path and header matching,
header modification, URL rewrite, request mirroring, timeouts, CORS) are
portable when an implementation's conformance report lists them. Consumer
management, JWT validation, and rate limiting are implementation-specific
policies attached to routes (for example Envoy Gateway's `SecurityPolicy` and
`BackendTrafficPolicy`).

Implementations to evaluate include Envoy Gateway and the Gateway API support
in other proxies and cloud load balancers (for example Application Gateway for
Containers on Azure). Compare them on conformance level for the features you
need, policy attachment model, release cadence, and who supports it. See
[Kubernetes Gateway API](kubernetes-gateway.md) and the
[Gateway](../assets/k8s/api-gateway.yaml.template),
[HTTPRoute](../assets/k8s/api-httproute.yaml.template), and
[SecurityPolicy](../assets/k8s/security-policy.yaml.template) templates.

Ingress NGINX status: Kubernetes SIG Network and the Security Response
Committee announced on 2025-11-11 that best-effort maintenance would continue
only until March 2026, after which the project is retired with no further
releases, bug fixes, or security updates. Existing installations keep working
but are unpatched. Do not choose it for new clusters; migrate existing ones to
a Gateway API implementation (or, if you must keep the Ingress API, another
maintained Ingress controller). Prefer the Gateway API for new clusters. The
migration procedure belongs to `kit-edge-networking`.

### Amazon API Gateway

Pick the API type first; it decides the feature set (verified 2026-10 on
AWS's REST-versus-HTTP comparison):

- REST API when you need API keys with usage plans (per-consumer throttling
  and quotas), caching, request validation, AWS WAF, private endpoints,
  canary deployments, or a developer portal.
- HTTP API for token-authenticated first-party clients: native JWT
  authorizers, stage and route throttling (not per client), automatic
  deployments, lower price. It has no usage plans or API keys.
- WebSocket API for two-way messaging, with a Lambda or IAM authorizer on
  `$connect`.

Template: [HTTP API with JWT authorizer](../assets/aws/api-gateway-http.tf.template).

### Google Cloud API Gateway and Apigee

- API Gateway: an OpenAPI-configured (2.0, 3.0.x, 3.1.x) managed gateway for
  Google Cloud backends with JWT or API-key authentication and per-API quotas.
  Template: [API Gateway from OpenAPI](../assets/gcp/api-gateway.tf.template).
- Apigee and Apigee hybrid: full API management (proxies, policies, API
  products, developer apps, portals, analytics, AI token policies). Choose it
  when plans, partner onboarding, or rich mediation are real needs; hybrid
  keeps the runtime in your own Kubernetes clusters.

### Other gateways

The [capability matrix](cloud-equivalents.md) compares all of the above with
Kubernetes options. Kong, Tyk, and similar products cover the same
concepts (consumers, plugins or policies, rate limits, portals). Evaluate them
with the same table: licensing and edition terms (verify the current terms of
the edition you would run), how policy is stored as code, how counters are
shared across nodes, and how configuration is promoted between environments.
Avoid running two gateway products in series unless each owns a distinct
concern.

## Decision record

Write a short record in the repository before provisioning:

1. The needs from the first table that justify the gateway, with consumers named.
2. The responsibility split per concern (copy the second table and fill it).
3. The chosen product and tier or implementation, the feature-matrix rows that
   decided it, and the verification date.
4. What happens when the gateway is down: fail closed for protected APIs; no
   bypass route that skips authentication.
5. The exit plan: contracts and policies in Git, so a different gateway can be
   rebuilt from the repository.

## Sources

- Azure API Management tier feature comparison:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-features>
- Azure API Management v2 tiers:
  <https://learn.microsoft.com/en-us/azure/api-management/v2-service-tiers-overview>
- Self-hosted gateway overview:
  <https://learn.microsoft.com/en-us/azure/api-management/self-hosted-gateway-overview>
- Workspaces in API Management:
  <https://learn.microsoft.com/en-us/azure/api-management/workspaces-overview>
- Ingress NGINX retirement announcement (2025-11-11):
  <https://kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/>
- Kubernetes Gateway API concept page:
  <https://kubernetes.io/docs/concepts/services-networking/gateway/>
- Gateway API project guides: <https://gateway-api.sigs.k8s.io/guides/>
- Gateway API releases (v1.6.3 latest stable at verification):
  <https://github.com/kubernetes-sigs/gateway-api/releases>
- Envoy Gateway documentation: <https://gateway.envoyproxy.io/docs/>
- Amazon API Gateway, REST versus HTTP APIs (verified 2026-10):
  <https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html>
- Google Cloud API Gateway overview (verified 2026-10):
  <https://cloud.google.com/api-gateway/docs/about-api-gateway>
- What is Apigee (verified 2026-10):
  <https://cloud.google.com/apigee/docs/api-platform/get-started/what-apigee>
