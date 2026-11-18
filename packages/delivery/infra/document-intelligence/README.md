# Azure Document Intelligence (opt-in)

One Document Intelligence resource (`Microsoft.CognitiveServices/accounts`,
kind `FormRecognizer`) for OCR with the `prebuilt-read` and `prebuilt-layout`
models, and an analyze grant for the app's **existing** identity.
Authentication is Entra ID only: local (key) authentication is disabled, the
custom subdomain that Entra ID needs is set and no key or secret is read or
output. Choose **one** canonical implementation: [Bicep](bicep/main.bicep)
**or** [Terraform](terraform/main.tf), never both over the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Reference `bicep/main.bicep` as a
resource-group-scoped module or `terraform` as a local Terraform child module.
The caller owns the resource group, identity, network, provider authentication
and state.

This is a separate resource rather than the Foundry resource because Microsoft
requires a single-service resource for Document Intelligence with Entra ID
authentication; see [REFERENCE.md](REFERENCE.md#why-a-separate-resource).

## What is included

| Part | Reason |
| --- | --- |
| Document Intelligence resource | `FormRecognizer`, `S0`, custom subdomain `name`, local auth disabled. |
| Role assignment | `Cognitive Services User` for `principalId`; on this single-service resource it allows Document Intelligence only. |
| Private endpoint and DNS zone group | Only when `privateEndpoint` is supplied. Public network access is disabled unless dev or test opts in. |
| Diagnostic settings | Only when `logAnalyticsWorkspaceId` is supplied: `allLogs` and `AllMetrics` to that workspace. |
| Production `CanNotDelete` lock | Toolkit production policy, scoped to the resource only. |
| Input guards | Reject unsafe combinations before deployment; they do not prove permissions or capacity. |

## Inputs

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Required | Meaning |
| --- | --- |
| `location` | Azure public-cloud region |
| `name` | 2–64 characters, globally unique; also the custom subdomain |
| `stage` | `dev`, `test`, `staging`, `prod`; separate names/groups/state per stage |
| `principalId` | Object (principal) ID of the existing app identity, **not** its client ID |
| `resource_group_id` | Terraform only: existing resource group ARM ID |

Optional: `privateEndpoint` (none), `allowPublicNetworkAccess` (`false`),
`allowedIpRanges` (`[]`) and `logAnalyticsWorkspaceId` (none, no
diagnostics; an empty string is rejected). `privateEndpoint` holds `subnetId` and `privateDnsZoneId`: an
existing `privatelink.cognitiveservices.azure.com` zone linked to the VNet. Pass
the workspace ARM ID in canonical casing.

| Stage | Network | Diagnostics | Lock |
| --- | --- | --- | --- |
| `dev`, `test` | Public access disabled by default; private endpoint, or `allowPublicNetworkAccess` with a deny-by-default `allowedIpRanges` ACL, optional | Optional workspace | None |
| `staging` | **Private endpoint required**; public access disabled | **Workspace required** | None |
| `prod` | **Private endpoint required**; public access disabled | **Workspace required** | `CanNotDelete` |

Staging gets every production guard except the lock, so it can be torn down
freely. Breaking change: dev and test callers that relied on the public
endpoint must now set `allowPublicNetworkAccess` (and their client ranges).

Outputs: `documentIntelligenceResourceId` and `endpoint`
(`https://<name>.cognitiveservices.azure.com/`).

## OCR usage

Call the GA v4.0 API with an Entra ID token for
`https://cognitiveservices.azure.com/.default`, for example with the
`azure-ai-documentintelligence` SDK and a managed-identity credential:

```text
POST {endpoint}documentintelligence/documentModels/prebuilt-read:analyze?api-version=2024-11-30
POST {endpoint}documentintelligence/documentModels/prebuilt-layout:analyze?api-version=2024-11-30
```

Poll the returned `Operation-Location` until the result is ready. `S0` limits:
15 analyze requests per second (adjustable through support), 500 MB and 2,000
pages per document. This package adds no client dependency.

## Verify and adopt

From the repository root using installed tools:

```powershell
uv run --locked pytest tests\integration\delivery\infra\test_document_intelligence.py -q
```

The tests use the same Bicep 0.39.26 / Terraform 1.11.3 baseline and
**Azure/azapi 2.13.0** pin as Container Apps. Full Terraform validation reuses
the `CONTAINER_APPS_AZAPI_MIRROR` provider mirror. Missing tools or providers
are skips, not live validation.

Before adoption, rollback is removal of these sources and their test. After
adoption, DNS records, locks and logs already sent to the workspace are not
undone by a source revert.
See [operator gates, rollback and sources](REFERENCE.md).
