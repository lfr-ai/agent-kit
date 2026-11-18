# Microsoft Foundry (opt-in)

One Microsoft Foundry resource (`Microsoft.CognitiveServices/accounts`, kind
`AIServices`, project management enabled), one Foundry project, the model
deployments the caller lists and data-plane roles for the app's **existing**
identity. Authentication is Entra ID only: local (key) authentication is
disabled, the custom subdomain is set and no key or secret is read or output.
Choose **one** canonical implementation: [Bicep](bicep/main.bicep) **or**
[Terraform](terraform/main.tf), never both over the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Reference `bicep/main.bicep` as a
resource-group-scoped module or `terraform` as a local Terraform child module.
The caller owns the resource group, identity, network, quota, provider
authentication and state.

## What is included

| Part | Reason |
| --- | --- |
| Foundry resource | `AIServices`, `S0`, system-assigned identity, custom subdomain `name`, local auth disabled. |
| Foundry project | One project, named like the resource, for the project endpoint. |
| Model deployments | Exactly the `deployments` list, created one at a time. The module has no default model. |
| Role assignments | `Cognitive Services OpenAI User` on the resource and `Foundry User` (formerly `Azure AI User`) on the project, for `principalId` only. |
| Private endpoint and DNS zone group | Only when `privateEndpoint` is supplied. Public network access is disabled unless dev or test opts in. |
| Diagnostic settings | Only when `logAnalyticsWorkspaceId` is supplied: `allLogs` and `AllMetrics` to that workspace. |
| Production `CanNotDelete` lock | Toolkit production policy, scoped to the Foundry resource (inherited by its project and deployments). |
| Input guards | Reject unsafe combinations before deployment; they do not prove permissions, quota or model availability. |

## Inputs

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Required | Meaning |
| --- | --- |
| `location` | Azure public-cloud region that offers the models and deployment types you list |
| `name` | 2–64 characters, globally unique; also the custom subdomain and the project name |
| `stage` | `dev`, `test`, `staging`, `prod`; separate names/groups/state per stage |
| `principalId` | Object (principal) ID of the existing app identity, **not** its client ID |
| `resource_group_id` | Terraform only: existing resource group ARM ID |

`deployments` is optional and defaults to `[]` (no model deployed).
Each deployment has `name` (what clients pass as `model`), `model`, `version`,
`sku` (deployment type such as `GlobalStandard` or `DataZoneStandard`),
`capacity` (units; one unit is 1,000 tokens per minute for standard types) and
an optional `format` (`OpenAI` unless set; use the catalog format for other
models sold directly by Azure). `DataZoneStandard` keeps processing inside the
Microsoft data zone (EU or US); `GlobalStandard` may process in any region.
Current example only; check region, quota and retirement date before use:

```bicep
param deployments = [
  {
    name: 'gpt-5.4-mini'
    model: 'gpt-5.4-mini'
    version: '2026-03-17'
    sku: 'GlobalStandard'
    capacity: 10
  }
]
```

Optional: `deployments` (`[]`), `privateEndpoint` (none),
`allowPublicNetworkAccess` (`false`), `allowedIpRanges` (`[]`),
`allowAllPublicClients` (`false`) and
`logAnalyticsWorkspaceId` (none, no diagnostics; an empty string is rejected).
`allowAllPublicClients`
needs `allowPublicNetworkAccess` with no `allowedIpRanges` and opens the
endpoint to every network. Local keys stay disabled, so callers still need an
Entra token and a role. It suits dev callers without fixed egress, such as
Container Apps outside a virtual network. `privateEndpoint` holds
`subnetId` and `privateDnsZoneIds`: the three existing zones
`privatelink.cognitiveservices.azure.com`, `privatelink.openai.azure.com` and
`privatelink.services.ai.azure.com`, each linked to the VNet and passed as an
exact-case ARM ID. Pass the workspace ARM ID in canonical casing.

| Stage | Network | Diagnostics | Lock |
| --- | --- | --- | --- |
| `dev`, `test` | Public access disabled by default; private endpoint, or `allowPublicNetworkAccess` with a deny-by-default `allowedIpRanges` ACL (or `allowAllPublicClients` for an Entra-only endpoint open to every network), optional | Optional workspace | None |
| `staging` | **Private endpoint with all three zones required**; public access disabled | **Workspace required** | None |
| `prod` | **Private endpoint with all three zones required**; public access disabled | **Workspace required** | `CanNotDelete` |

Staging gets every production guard except the lock, so it can be torn down
freely. Breaking change: dev and test callers that relied on the public
endpoint must now set `allowPublicNetworkAccess` (and their client ranges).

Outputs: `foundryResourceId`, `projectResourceId`, `openAiEndpoint`
(`https://<name>.openai.azure.com/openai/v1/`) and `projectEndpoint`
(`https://<name>.services.ai.azure.com/api/projects/<name>`).

Call deployments through `openAiEndpoint` with any OpenAI-compatible client and
an Entra ID token for `https://ai.azure.com/.default`; `Cognitive Services
OpenAI User` is the least-privileged built-in role for that. Use
`projectEndpoint` with the Foundry SDK (agents, responses, evaluations); the
project-scoped `Foundry User` grant covers it. `Cognitive Services OpenAI User`
covers OpenAI models only; other models need an additional, reviewed grant (see
[REFERENCE.md](REFERENCE.md)). This package adds no client dependency.

OCR (`prebuilt-read`, `prebuilt-layout`) uses the separate
[Document Intelligence composition](../document-intelligence/README.md):
Microsoft requires a single-service resource for Document Intelligence with
Entra ID authentication. See [REFERENCE.md](REFERENCE.md#ocr-decision).

## Verify and adopt

From the repository root using installed tools:

```powershell
uv run --locked pytest tests\integration\delivery\infra\test_ai_foundry.py -q
```

The tests use the same Bicep 0.39.26 / Terraform 1.11.3 baseline and
**Azure/azapi 2.13.0** pin as Container Apps. Full Terraform validation reuses
the `CONTAINER_APPS_AZAPI_MIRROR` provider mirror. Missing tools or providers
are skips, not live validation.

Before adoption, rollback is removal of these sources and their test. After
adoption, deployed models, DNS records, locks and logs already sent to the
workspace are not undone by a source revert.
See [operator gates, rollback and sources](REFERENCE.md).
