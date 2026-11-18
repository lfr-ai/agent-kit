# API Management: operator gates, validation and sources

Start with the [consumer contract](README.md).

## Defaults this composition relies on

The sources declare only what differs from the platform default or what the API
requires (`sku.capacity`, `publisherEmail`, `publisherName`, API `path` and
`protocols`, the logger and diagnostic IDs). They deliberately **do not
restate** these defaults:

- Instance: public network access enabled and no virtual network.
- API: `http` type; policy content is read as XML.
- `rate-limit-by-key`: `429 Too Many Requests` with a `Retry-After` header.
- `validate-azure-ad-token`: reads the `Authorization` bearer token and answers
  `401` on failure. Signing keys come from the tenant's Entra metadata.
- Logger and diagnostic: buffered logging and the service sampling defaults.

Policy order is token validation, then the rate limit, then the optional LLM
token limit. Token validation therefore rejects anonymous requests before they
consume a caller's budget. An optional operator-owned edge WAF may absorb floods of
invalid tokens.

## Operator gates and ownership

- **Entra.** The backend's app registration exposes the audience: an
  Application ID URI such as `api://…` or its client ID. Clients obtain tokens
  for it. The policy only checks issuer tenant, audience, signature and
  lifetime. Add `required-claims` (roles or scopes) in
  [validate-token.xml](policies/validate-token.xml) when callers must hold an
  app role.
- **Backend.** The gateway forwards to `backendUrl` over the public internet.
  The backend must accept the gateway's traffic. To keep it private, add
  Standard v2 outbound VNet integration after review. The backend should still
  authorize the caller itself; the gateway forwards the caller's
  `Authorization` header unchanged.
- **Wildcard operations.** One API forwards every path on five methods.
  Microsoft warns that wildcard operations hide the real API inventory from
  API Management. Replace them with explicit operations or an OpenAPI import
  when the backend contract is stable.
- **Rate limits.** v2 tiers count with a token bucket, and Microsoft notes that
  distributed rate limiting is never exact. `requestsPerMinute` is a fairness
  limit per caller, not a billing quota. Use `quota-by-key`, products or app
  logic for long-period quotas.
- **AI gateway.** `llmTokensPerMinute` adds `llm-token-limit` and
  `llm-emit-token-metric`. Both support Azure OpenAI and OpenAI-compatible chat
  APIs. `estimate-prompt-tokens="false"` counts tokens from the backend's
  response usage, which is cheaper but lets one oversized request through
  before the limit applies. Metrics need the logger and `metrics: true`, which
  this composition sets. In Application Insights, enable **Custom metrics
  (Preview) with dimensions** by hand; Azure Monitor custom metrics are still a
  preview feature.
- **Application Insights.** The component must be in the instance's resource
  group. The logger sends data with the system identity, and the composition
  grants `Monitoring Metrics Publisher` on the component. The deploying
  identity therefore needs `Microsoft.Authorization/roleAssignments/write` on
  it. The connection string is read from the component at deployment.
  Microsoft documents it as a target identifier, not a secret, and it is never
  an input or output. Once every sender uses Entra, disable local
  authentication on the component.
- **Logs.** `GatewayLogs` go to the resource-specific
  `ApiManagementGatewayLogs` table in an existing workspace (required in
  staging and production). Ingestion and retention are billed by the workspace.
- **Lock.** The production lock covers the instance and blocks deletion only. It
  does not block configuration changes or an actor who may remove locks.
  Terraform destroy removes its own lock first; operator approvals must deny
  unreviewed destroy, replacement and lock removal.
- **Terraform read-back.** API Management reformats policy XML and masks logger
  credentials on read. After the first apply, run a second plan and confirm it
  is empty. If it is not, add a reviewed `lifecycle { ignore_changes }` or move
  to a provider version with write-only support. The pinned Terraform's mock
  tests reject write-only attributes, so this composition does not use them.
- **Names.** Instance names are global and DNS-visible; the gateway host is
  `<name>.azure-api.net`.

## Offline checks and pins

Checked tool baseline: **Bicep 0.39.26** and **Terraform 1.11.3**. Terraform
pins **Azure/azapi 2.13.0**. The repository's other Terraform compositions also
use azapi rather than azurerm, so one provider and one mirror cover all of
them. API versions: `Microsoft.ApiManagement` 2024-05-01 (the newest GA in the
Bicep type index; later versions are preview), `Microsoft.Insights/components`
2020-02-02, role assignments 2022-04-01, locks 2020-05-01 and
`Microsoft.Insights/diagnosticSettings` 2021-05-01-preview (the version AVM and
the sibling compositions use; no GA version adds anything needed here).

Both sources load the same files from [policies](policies). Optional fragments
replace marker comments in `api.xml`, so each file stays well-formed XML, and
the integration test parses them. The test also relocates the exact source
closure and runs Bicep format, lint, `build` and `build-params` for the dev
and prod examples. It evaluates the exported guards with Bicep's parameter
evaluator and runs the same cases against the **unchanged variables.tf alone**
with `terraform test`. Full resource validation and the mocked plans in
`terraform/tests` need the reviewed Azure/azapi 2.13.0 mirror. Set
`CONTAINER_APPS_AZAPI_MIRROR`; tests then run
`terraform init -backend=false -input=false -plugin-dir=<mirror>`.
**No mirror means a reported skip, not a provider-validation pass.** Mocks do
not certify ARM behavior, policy evaluation or permissions.

## Rollback

Before deployment, remove this directory, its integration test, its catalog
entry and the delivery README row; no cloud state has changed. After adoption,
revert inputs through the owning IaC tool and review the plan. Removing the
production lock is a reviewed step before any delete. A deleted instance is
soft-deleted for 48 hours and keeps its name until it is purged or recovered.
Turning token validation off or raising limits takes effect at once and
reopens the API, so review it like an access change. A Bicep incremental
deployment leaves a removed role assignment, logger or diagnostic setting in
place, so delete it explicitly. Logs and metrics already ingested stay for the
workspace's retention period. Never switch Bicep/Terraform ownership by
applying the other source; review import and state migration first.

## Sources

Checked on 2026-11-11:

- [v2 tiers overview](https://learn.microsoft.com/en-us/azure/api-management/v2-service-tiers-overview),
  [feature comparison by tier](https://learn.microsoft.com/en-us/azure/api-management/api-management-features)
  and [private endpoints for the gateway](https://learn.microsoft.com/en-us/azure/api-management/private-endpoint)
  (Standard v2 and Premium v2 can sit behind an operator-owned edge).
- [rate-limit-by-key](https://learn.microsoft.com/en-us/azure/api-management/rate-limit-by-key-policy),
  [quota-by-key](https://learn.microsoft.com/en-us/azure/api-management/quota-by-key-policy)
  and [advanced request throttling](https://learn.microsoft.com/en-us/azure/api-management/api-management-sample-flexible-throttling).
- [validate-azure-ad-token](https://learn.microsoft.com/en-us/azure/api-management/validate-azure-ad-token-policy)
  and [validate-jwt](https://learn.microsoft.com/en-us/azure/api-management/validate-jwt-policy).
- [llm-token-limit](https://learn.microsoft.com/en-us/azure/api-management/llm-token-limit-policy),
  [llm-emit-token-metric](https://learn.microsoft.com/en-us/azure/api-management/llm-emit-token-metric-policy)
  and [AI gateway capabilities](https://learn.microsoft.com/en-us/azure/api-management/genai-gateway-capabilities).
- [Application Insights logger with managed identity](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-app-insights)
  and [connection strings](https://learn.microsoft.com/en-us/azure/azure-monitor/app/connection-strings).
- [Wildcard operations and API inventory](https://learn.microsoft.com/en-us/azure/api-management/mitigate-owasp-api-threats)
  and [soft delete](https://learn.microsoft.com/en-us/azure/api-management/soft-delete).
- [Resource logs to Log Analytics](https://learn.microsoft.com/en-us/azure/api-management/monitor-api-management)
  and [schemas](https://learn.microsoft.com/en-us/azure/templates/microsoft.apimanagement/2024-05-01/service),
  [role assignments](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2022-04-01/roleassignments)
  and [locks](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2020-05-01/locks).
- [API Management REST specification](https://github.com/Azure/azure-rest-api-specs/tree/main/specification/apimanagement/resource-manager)
  (2024-05-01 property defaults).
