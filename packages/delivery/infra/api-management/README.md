# Azure API Management (opt-in)

One API Management v2 instance with one API that forwards every path to an
**existing** HTTPS backend, such as a Container App. Each caller is rate limited
on the gateway. In staging and production every caller must present an Entra
token. The
instance has a system-assigned identity; no subscription keys, secrets or
connection strings are taken as inputs or returned. Choose **one** canonical
implementation: [Bicep](bicep/main.bicep) **or** [Terraform](terraform/main.tf),
never both over the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Reference `bicep/main.bicep` as a
resource-group-scoped module or `terraform` as a local Terraform child module.
The caller owns the resource group, backend, Entra app registration, workspace,
Application Insights component, provider authentication and state.

## What is included

| Part | Reason |
| --- | --- |
| API Management v2, system-assigned identity | Basic v2 in dev/test/staging, Standard v2 in production. See the tier note below. |
| API `backend` at the gateway root | `GET`, `POST`, `PUT`, `PATCH` and `DELETE` on `/*` forward to `backendUrl`; no subscription key. |
| [API policy](policies/api.xml) | Entra token validation when configured, then a per-caller rate limit. |
| [AI gateway policies](policies/llm-tokens.xml) | Only when `llmTokensPerMinute` is above 0: an LLM token limit per caller and a token-usage metric. |
| Application Insights logger | Only when `applicationInsightsName` is set. It uses the managed identity and a `Monitoring Metrics Publisher` grant, not a key. |
| `GatewayLogs` diagnostic setting | Only when `logAnalyticsWorkspaceId` is set, written to the resource-specific `ApiManagementGatewayLogs` table. |
| Production `CanNotDelete` lock | Toolkit production policy, scoped to the instance only. |
| Input guards | Reject unsafe staging and production inputs before deployment; they do not prove permissions or capacity. |

**Tier.** Basic v2 is Microsoft's v2 tier for development and testing.
Production uses Standard v2. It is the smallest v2 production tier that
accepts an inbound private endpoint, which a Private Link origin of an optional
operator-owned edge needs, and it supports outbound VNet integration to a private backend.
Neither tier gets the classic tiers' VNet injection. Use Premium v2 for that or
for multi-region, and change the SKU in the source after review.

## Inputs

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Required | Meaning |
| --- | --- |
| `location` | Azure region |
| `name` | 1–50 characters, globally unique; the gateway is `https://<name>.azure-api.net`. Separate names per stage. |
| `stage` | `dev`, `test`, `staging`, `prod` |
| `publisherEmail` | Address for API Management system notifications |
| `backendUrl` | `https://` base URL of the backend, for example the Container App URL |
| `resource_group_id` | Terraform only: existing resource group ARM ID |

| Optional | Default | Meaning |
| --- | --- | --- |
| `entraTenantId`, `entraAudience` | none (no token check) | Set both together; empty strings are rejected. The audience is the backend app registration's Application ID URI or client ID. |
| `requestsPerMinute` | `120` | Calls per minute per caller before `429 Too Many Requests` with `Retry-After` |
| `llmTokensPerMinute` | `0` (off) | Per-caller LLM token budget for an Azure OpenAI or OpenAI-compatible backend. Needs `applicationInsightsName`. |
| `applicationInsightsName` | none (no telemetry) | Existing component **in the same resource group**; an empty string is rejected |
| `logAnalyticsWorkspaceId` | none (no diagnostics) | Existing workspace ARM ID in canonical casing; an empty string is rejected |

| Stage | SKU | Caller token | Gateway logs | Lock |
| --- | --- | --- | --- | --- |
| `dev`, `test` | `BasicV2`, 1 unit | Optional | Optional workspace | None |
| `staging` | `BasicV2`, 1 unit | **Entra token required** | **Workspace required** | None |
| `prod` | `StandardV2`, 1 unit | **Entra token required** | **Workspace required** | `CanNotDelete` |

Staging gets the production security guards (token and gateway logs) but keeps
Basic v2 and no lock: Standard v2 costs more per unit, and staging must be easy
to tear down. Basic v2 has no inbound private endpoint, so a staging private-link
origin from an operator-owned edge needs Standard v2; change the SKU after review if staging
must mirror production networking.

The caller is the `sub` claim of the validated token. Without token validation
it is the client IP. Behind an optional operator-owned edge that may be an edge address shared by many
clients, so in dev and test turn on token validation or raise the limit.

Outputs: instance resource ID, gateway URL and the identity's principal ID.
Grant that principal access to the backend only if the backend itself
authenticates the gateway.

## Rate limiting layers

| Layer | Key | Response | Use it for |
| --- | --- | --- | --- |
| Optional edge WAF (operator-owned, not shipped here) | Client IP, counted per edge location | `403` | A coarse flood guard in front of everything, unauthenticated traffic included |
| Gateway, this module | Token subject (client IP without a token) | `429` with `Retry-After` | Fair use per caller, and LLM token budgets |
| Application | Anything the app knows: tenant, plan, resource | App-defined | Business rules such as quotas per customer or per expensive operation |

Simple case: keep the edge default and set `requestsPerMinute` for a normal
caller. Add app-level limits only when a rule depends on business data. Each
layer counts on its own, so keep the edge limit well above what one IP sends
legitimately; it should only stop floods.

## Minimal example

```bicep
module gateway 'api-management/bicep/main.bicep' = {
  params: {
    location: 'westeurope'
    name: 'sample-apim-dev'
    stage: 'dev'
    publisherEmail: 'platform@example.com'
    backendUrl: 'https://sample-app.example.com'
  }
}
```

The [production example](bicep/tests/prod.bicepparam) adds the token and
workspace inputs. Terraform takes the same inputs in snake_case plus
`resource_group_id`; see [the plan tests](terraform/tests/api-management.tftest.hcl).

## Verify and adopt

From the repository root using installed tools:

```powershell
uv run --locked pytest tests\integration\delivery\infra\test_api_management.py -m integration -q
```

The tests use the Bicep 0.39.26 / Terraform 1.11.3 baseline and the
**Azure/azapi 2.13.0** pin. Full Terraform validation reuses the
`CONTAINER_APPS_AZAPI_MIRROR` provider mirror. Missing tools or providers are
skips, not live validation.

Before adoption, rollback is removal of these sources and their test. After
adoption, a deleted instance stays soft-deleted for 48 hours and holds its name.
The role assignment, locks, and logs and metrics already sent are not undone by
a source revert.
See [operator gates, rollback and sources](REFERENCE.md).
