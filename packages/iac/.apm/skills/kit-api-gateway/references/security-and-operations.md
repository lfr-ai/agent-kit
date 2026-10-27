# Security and operations for an API gateway

Verified as of 2026-10 against the sources listed at the end. Applies to
Azure API Management first; the same questions apply to any gateway. Record the
answers in the [review worksheet](../assets/gateway-review.md.template).

## Authentication: gateway and service, not either-or

| Check | Gateway | Service |
| --- | --- | --- |
| Token present, signed, unexpired, right issuer and audience | Yes (reject early, save backend capacity) | Yes (authoritative; the gateway can be bypassed or misconfigured) |
| Coarse scope or role per API | Yes | Yes |
| Object-level authorization and tenant isolation | No | Yes |
| Consumer identity for limits (subscription, client ID) | Yes | Optional, from a header the gateway sets |

- Defense in depth: the service must reject requests that did not come
  through the gateway. Combine network isolation (backends reachable only from
  the gateway) with service authentication (a managed-identity token issued to
  the gateway, or mTLS), and keep the service's own token validation
  (`kit-auth`).
- Never forward an "authenticated user" header from the gateway that the
  service trusts without verifying where it came from; a caller can send the
  same header if any path skips the gateway.
- Subscription keys identify consumers for limits and analytics; they are
  not user authentication. Use them together with tokens for partner APIs, or
  alone only for low-risk public data.

## Client certificates and mTLS

- Client to gateway: enable client certificate negotiation for the
  hostname (classic tiers request it per custom hostname; the Consumption tier
  has an instance setting), then check it with `validate-client-certificate`
  (issuer, subject, thumbprint, validity). Feature availability differs by
  tier; v2 tiers do not support client certificate renegotiation.
- When TLS terminates at Front Door or Application Gateway in front of the
  gateway, the client certificate does not reach the gateway; terminate mTLS
  at the first hop or pass the certificate in a header only that hop can set,
  and document which hop owns the check (`kit-edge-networking`).
- Gateway to backend: attach a client certificate (from Key Vault) to the
  backend entity, or prefer managed identity tokens. On v2 tiers custom CA
  certificates for backend validation are configured on the backend entity.
- Keep backend certificate chain and name validation on; disabling it turns
  TLS into encryption without authentication.

## Network exposure

| Pattern | Use when | Tier notes (check the matrix) |
| --- | --- | --- |
| Public gateway, public backends with service auth | Small surface, strong service auth | All tiers |
| Public gateway, backends in a VNet | Backends must not be internet-reachable | VNet integration in Standard v2/Premium v2; VNet injection in Developer/Premium classic |
| Private endpoint for inbound gateway traffic | Consumers are inside private networks | Developer, Basic, Standard, Premium classic; Standard v2, Premium v2 |
| Fully injected (internal) gateway behind an edge | Regulated or private-only APIs | Premium, Developer classic; Premium v2 |

- With an edge in front (Front Door or Application Gateway with WAF), lock
  the gateway down to that edge: an `ip-filter` for the edge's service tag
  ranges (or a network security group rule when injected) and a `check-header`
  on the edge's identifying header (for Front Door, `X-Azure-FDID` compared
  with a named value). Otherwise the WAF can be bypassed by calling the gateway
  host directly.
- `ip-filter` is a coarse allow or deny list. It does not replace
  authentication, and behind a proxy it sees the proxy's address.
- Disable the developer portal and the legacy portal when not used; set
  `publicNetworkAccess` to `Disabled` only after a private path exists.
- Minimum TLS: disable TLS 1.0 and 1.1 for client and backend sides (the
  instance's protocol settings, shown in
  [apim.bicep](../assets/bicep/apim.bicep.template)).

## WAF and abuse protection

- The WAF, bot protection, geo rules, and volumetric DDoS protection belong to
  the edge (`kit-edge-networking`), not to gateway policies. The gateway adds
  per-consumer limits and request validation behind it.
- Keep request body limits at each hop, ordered so the innermost limit is
  the smallest that still serves the contract (`validate-content max-size`).

## Observability

- Send gateway request telemetry to Application Insights through a logger
  that authenticates with the instance's managed identity (connection string
  plus `identityClientId`, and the Monitoring Metrics Publisher role).
- Send resource logs (gateway logs, and model logs for AI APIs) and metrics to
  Log Analytics through diagnostic settings for dashboards and alerts.
- Sampling: keep 100% in non-production; in production pick a fixed
  percentage that fits the ingestion budget and set `alwaysLog` to all errors so
  failures are never sampled away.
- Log no request or response bodies and no header values by default; add
  specific headers only after review, and mask query parameters that carry
  secrets.
- Use W3C trace context for correlation so the gateway span joins the
  service's trace (`kit-observability`).
- Custom and token metrics: few dimensions with few distinct values; never a
  user or request identifier as a dimension.

## SLOs and alerts

Define the gateway hop's own indicators and alert on burn rate rather than raw
thresholds (`kit-observability` owns the method):

| Signal | Source | Why |
| --- | --- | --- |
| Gateway 5xx share, excluding backend 5xx | Gateway logs (`BackendResponseCode` vs `ResponseCode`) | Separates gateway faults from service faults |
| 429 and 403 rate per product | Gateway logs | Shows limits that are too tight or abuse |
| Latency p95/p99 split into gateway and backend time | Request telemetry | Policy cost versus backend cost |
| Capacity or CPU/memory of the gateway | Platform metrics | Scale before saturation |
| Circuit breaker trips | Gateway logs and backend 503s | Backend health from the gateway's view |
| Certificate expiry, Key Vault access failures | Activity and resource logs | Silent outages waiting to happen |

## Capacity and scale

- Scale units set throughput and price; the maximum per tier is in the
  feature matrix (for example up to 10 units for Basic v2 and Standard v2 and
  30 for Premium v2 at the verification date). Load-test with production-like
  policies before choosing the unit count: policies with expressions,
  validation, and transformation cost CPU.
- Use autoscale where the tier supports it, triggered on the capacity or CPU
  metric, with a minimum that survives a zone or unit loss.
- Large bodies, buffering, and streaming responses change capacity; test
  them explicitly, especially for model APIs.

## Disaster recovery and multi-region

- Everything except runtime data (subscriptions, users, portal content
  edits) is in Git, so recovery is "redeploy the last good commit". Export or
  script subscriptions so they can be restored, or accept re-onboarding.
- Classic Premium supports multi-region gateways and availability zones;
  Premium v2 supports zones; v2 tiers lack multi-region deployment and backup
  and restore at the verification date. For regional failure on v2, run a
  second instance in another region behind a global edge, deployed from the
  same commit, and fail over at the edge.
- Remember that rate-limit and token counters are per regional gateway: an
  active-active pair doubles the effective limit unless limits are divided.
- Practice failover: measure redeploy time and DNS or edge switch time, and
  record the last drill in the worksheet.

## Cost

- The tier and unit count dominate; workspace gateways and self-hosted
  gateways are priced separately. Check the pricing page for the region.
- Telemetry ingestion can rival the gateway bill. Sample, avoid body logging,
  and set retention deliberately.
- An external cache, Front Door, and private networking add their own costs;
  include them in the estimate in the worksheet.

## Sources

- Gateway overview and feature comparison:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-gateways-overview>
- Tier feature comparison:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-features>
- Client certificate authentication:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-mutual-certificates-for-clients>
- Backend certificates and CA certificates:
  <https://learn.microsoft.com/en-us/azure/api-management/backends>
- Network concepts:
  <https://learn.microsoft.com/en-us/azure/api-management/virtual-network-concepts>
- Front Door in front of API Management:
  <https://learn.microsoft.com/en-us/azure/api-management/front-door-api-management>
- Protocols and ciphers:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-manage-protocols-ciphers>
- Application Insights integration:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-app-insights>
- Monitor API Management:
  <https://learn.microsoft.com/en-us/azure/api-management/monitor-api-management>
- Capacity: <https://learn.microsoft.com/en-us/azure/api-management/api-management-capacity>
- Autoscale:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-autoscale>
- Multi-region deployment:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-deploy-multi-region>
- Well-Architected service guide for API Management:
  <https://learn.microsoft.com/en-us/azure/well-architected/service-guides/azure-api-management>
