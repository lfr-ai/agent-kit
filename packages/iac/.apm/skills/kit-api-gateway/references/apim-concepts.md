# Azure API Management concepts

Verified as of 2026-10 against the sources listed at the end. The examples use
a neutral `shop` platform with an `orders` API; the matching Bicep is in
[api.bicep](../assets/bicep/api.bicep.template) and
[apim.bicep](../assets/bicep/apim.bicep.template).

## Object model

```text
service (instance, tier, identity, hostnames, network)
├── named values      reusable strings and Key Vault-backed secrets
├── backends          target URL, TLS, credentials, circuit breaker, pools
├── loggers/diagnostics  Application Insights or Event Hubs sinks
├── policy fragments  reusable policy XML included by id
├── policies          global scope
├── apiVersionSets    one per API family (versioning scheme)
│   └── apis          one per version (and per revision)
│       ├── operations   imported from the OpenAPI document
│       └── policies     API and operation scope
├── products          plans that group APIs
│   ├── apis           membership
│   ├── policies       product scope (plan limits)
│   └── groups         who can see and subscribe
├── subscriptions     keys issued to a consumer for a product, API, or all APIs
└── workspaces        team-owned subsets of the above (v2 and Premium)
```

## APIs and operations

- An API is a public facade: a path under the gateway host, a set of
  operations, and policies. Import it from the OpenAPI document that the API
  owner publishes (`kit-api-contracts`); do not author operations by hand in
  the portal, because the next import overwrites them and the contract and the
  gateway drift apart.
- The API's `path` is the public prefix. The backend URL lives on a backend
  entity (or the API's service URL) so that environments differ only in
  parameters.
- Operation-scope policies are for genuine per-operation differences (a larger
  body limit on an upload, a cache on a read). Most rules belong at API scope.
- Set `subscriptionRequired` deliberately. A subscription key identifies a
  consumer for limits and analytics; it is not user authentication.

## Products, subscriptions, and keys

- A product is a plan: a set of APIs, an approval rule, a visibility rule
  (groups), and product-scope policies such as quotas. Typical products are
  `orders-trial` (low quota, auto-approved) and `orders-standard` (approval
  required, contractual quota).
- A subscription belongs to a consumer and is scoped to a product, a single
  API, or all APIs. It carries a primary and a secondary key so consumers can
  rotate without downtime: switch to the secondary, regenerate the primary,
  switch back.
- Keys are sent in the `Ocp-Apim-Subscription-Key` header by default (a query
  parameter is also accepted unless you change the parameter names). Prefer the
  header; query strings end up in logs.
- Remove the key header in the inbound policy before forwarding so the service
  never sees or logs it.
- `rate-limit` and `quota` (the per-subscription variants) depend on a
  subscription key. When consumers authenticate only with tokens, use
  `rate-limit-by-key` and `quota-by-key` keyed on a token claim.
- Keys are bearer secrets. Treat them like passwords: deliver through the
  developer portal or a secret store, set an expiry or review date, and revoke
  on offboarding.

## Versions and revisions

| | Version | Revision |
| --- | --- | --- |
| Purpose | Breaking change; consumers opt in | Non-breaking change; staged and then made current |
| Consumer-visible | Yes, through a versioning scheme | Only the current revision by default |
| Addressing | Path segment (`/orders/v2`), header, or query parameter | `;rev=N` after the API path, for testing |
| Policies and operations | Independent per version | Copied from the source revision |
| Rollback | Consumers stay on the old version | Make the previous revision current again |

- Use the path-segment scheme unless a contract decision says otherwise; it is
  visible in logs and works with every client and cache.
- One API version set per API family; each version is its own `apis` resource
  named, for example, `orders-v1` and `orders-v2`.
- Decide the version boundary with the compatibility rules of
  `kit-api-contracts`; the gateway only exposes the decision.
- Revisions let you deploy, test with `;rev=N`, and switch. Properties such as
  path, protocols, version, and whether a subscription is required can only be
  changed on the current revision.
- Announce deprecation and sunset dates for old versions and keep them running
  until the published date.

## Named values

- Named values are key-value strings referenced in policies as
  `{{name}}`. Use them for every environment-specific or secret value so that
  the policy XML is identical in all environments.
- Three kinds: plain, secret (encrypted, masked in the portal), and Key
  Vault-backed. Use Key Vault-backed for every secret.
- The service reads Key Vault with its managed identity (system- or
  user-assigned) and needs the Key Vault Secrets User role (or an access policy
  on vaults that do not use RBAC).
- Reference the secret without a version. Updated secrets are picked up within
  four hours, or immediately with a manual refresh through the portal or
  management API. Secrets must be 1 to 4096 characters.
- A policy that references a missing named value fails to save. In Bicep,
  make the policy resource depend on the named values it uses.
- Named values are visible to anyone who can read the instance configuration
  unless they are secret or Key Vault-backed; never store credentials as plain
  named values.

## Backends

- A backend entity holds the target URL, TLS validation settings,
  credentials (header, query, client certificate, or managed identity), and an
  optional circuit breaker. Policies select it with
  `set-backend-service backend-id="..."`.
- Circuit breaker: one rule per backend at the verification date, defined by
  a failure count or percentage within an interval, a status-code range, and a
  trip duration; `acceptRetryAfter` honors the backend's `Retry-After`. While
  tripped, the gateway returns 503 without calling the backend. Tripping is
  approximate because gateway instances do not share state. Not available in
  the Consumption tier.
- Load-balanced pool: a backend of type `Pool` with up to 30 member backends
  using round-robin, weighted, or priority-based distribution, optionally with
  cookie-based session affinity. Lower priority groups receive traffic only
  when all higher-priority members are tripped, which makes "primary region
  first, secondary on failure" a configuration rather than code.
- Model backends often answer 429 with a long `Retry-After`; give them a
  circuit breaker that accepts it, inside a priority pool.

## Managed identity to backends

- Give the service a system-assigned identity (or a user-assigned one shared
  across instances in different regions).
- For Azure services, grant the identity a data-plane role on the target (for
  example a Cognitive Services role on a model deployment) and use
  `authentication-managed-identity` with that service's resource URI.
- For your own service, register an Entra application for it, grant the
  gateway identity an app role, send the token with
  `authentication-managed-identity resource="<app id URI>"`, and validate it in
  the service like any other caller (`kit-auth`). This replaces shared API keys
  between gateway and service.

## Environments

API Management has no built-in "environment" object. Use one instance per
environment (or per environment group: for example a shared Developer or Basic
v2 instance for dev and test, Standard v2 or Premium for production), deployed
from the same Bicep with different parameter files. Do not use workspaces,
products, or revisions to separate dev from prod: they share one gateway,
one set of named values, and one failure domain.

## Workspaces

Workspaces delegate a slice of an instance to a team: its APIs, products,
subscriptions, named values, and policies, with workspace-scope policy between
global and product scope. A workspace can be served by a dedicated workspace
gateway for isolation. Use them when several teams publish through one
platform-owned instance; keep global policy and network settings with the
platform team.

## Developer portal

- Generated from the published APIs and products; consumers sign up, read the
  contract, try operations, and obtain keys.
- Decide identity for portal users (Entra ID or another provider where the
  tier supports it) and who approves subscriptions.
- Keep it disabled until a real external audience exists; it is one more public
  surface to secure and customize.
- Content customizations are configuration; export and version them with the
  rest of the instance configuration.

## Sources

- API Management key concepts:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-key-concepts>
- Subscriptions:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-subscriptions>
- Versions: <https://learn.microsoft.com/en-us/azure/api-management/api-management-versions>
- Revisions: <https://learn.microsoft.com/en-us/azure/api-management/api-management-revisions>
- Named values:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-properties>
- Backends, circuit breaker, and pools:
  <https://learn.microsoft.com/en-us/azure/api-management/backends>
- Managed identities in API Management:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-use-managed-service-identity>
- Workspaces: <https://learn.microsoft.com/en-us/azure/api-management/workspaces-overview>
- Developer portal overview:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-developer-portal>
- Bicep resource reference, `Microsoft.ApiManagement` 2024-05-01:
  <https://learn.microsoft.com/en-us/azure/templates/microsoft.apimanagement/service>
