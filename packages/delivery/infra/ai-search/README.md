# Azure AI Search (opt-in)

One Azure AI Search service with index-data grants for the app's **existing**
managed identity and, optionally, an indexing identity. API keys are disabled:
callers authenticate with Entra ID and Azure RBAC only, and no key is read or
output.
Choose **one** canonical implementation: [Bicep](bicep/main.bicep) **or**
[Terraform](terraform/main.tf), never both over the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Reference `bicep/main.bicep` as a
resource-group-scoped module or `terraform` as a local Terraform child module.
The caller owns the resource group, identities, network, provider
authentication and state. Indexes, indexers and data sources are app content
and stay out of this composition.

## What is included

| Part | Reason |
| --- | --- |
| Search service | Basic in dev/test, Standard in production; API keys disabled. Only non-default settings are declared. |
| `Search Index Data Reader` | The app identity can query indexes, nothing more. |
| `Search Index Data Contributor` | Only when `indexingPrincipalId` is supplied: that identity can load documents into indexes. |
| Private endpoint and DNS zone group | Only when `privateEndpoint` is supplied. Public access is disabled unless dev or test opts in. |
| Diagnostic settings | Only when `logAnalyticsWorkspaceId` is supplied: `OperationLogs` and `AllMetrics` to that workspace. |
| Production `CanNotDelete` lock | Toolkit production policy, scoped to the search service only. |
| Input guards | Reject unsafe combinations before deployment; they do not prove permissions, quota or regional capacity. |

## Inputs

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Required | Meaning |
| --- | --- |
| `location` | Azure public-cloud region; production should have availability zones |
| `name` | Globally unique, 2–60 lowercase letters, digits or hyphens |
| `stage` | `dev`, `test`, `staging`, `prod`; separate names/groups/state per stage |
| `principalId` | Object (principal) ID of the existing app identity, **not** its client ID |
| `resource_group_id` | Terraform only: existing resource group ARM ID |

Optional: `indexingPrincipalId` (none), `replicaCount` (stage default),
`privateEndpoint` (none), `allowPublicNetworkAccess` (`false`),
`allowedIpRanges` (`[]`) and `logAnalyticsWorkspaceId` (none, no
diagnostics; an empty string is rejected). `privateEndpoint` holds `subnetId` and `privateDnsZoneId`. Both
must exist already, and the `privatelink.search.windows.net` zone must be
linked to the VNet. Public network access is disabled in every stage unless dev
or test sets `allowPublicNetworkAccess` with at least one `allowedIpRanges`
entry (Search treats an empty list as all networks).

| Stage | Network | Tier and replicas | Semantic ranker | Diagnostics | Lock |
| --- | --- | --- | --- | --- | --- |
| `dev`, `test` | Private by default, Entra ID only; private endpoint or explicit IP allow list optional | Basic, 1 replica (max 3) | Free plan (platform default, monthly allowance) | Optional workspace | None |
| `staging` | **Private endpoint required**; public access disabled | Basic, 1 replica (max 3) | Free plan | **Workspace required** | None |
| `prod` | **Private endpoint required**; public access disabled | Standard, **2 replicas** (read SLA); **fewer rejected**, set 3 for read-write SLA | Standard plan (billed beyond the free allowance) | **Workspace required** | `CanNotDelete` |

Staging gets the production security guards but keeps dev/test capacity: the
replica floor, Standard tier and semantic plan are cost decisions left to
production.

With two or more replicas, the service spreads them across availability zones
in regions that support zones; there is nothing to configure.

Outputs: search service ID and `endpoint` (`https://<name>.search.windows.net`).
Clients use an Entra token from the identity, for example the Azure AI Search
SDK `SearchClient` with `DefaultAzureCredential`, or
`ManagedIdentityCredential` with a user-assigned identity's *client* ID.
Role assignments can take 5–10 minutes to take effect. This package adds no
client dependency.

## Verify and adopt

From the repository root using installed tools:

```powershell
uv run --locked pytest tests\integration\delivery\infra\test_ai_search.py -q
```

The tests use the same Bicep 0.39.26 / Terraform 1.11.3 baseline and
**Azure/azapi 2.13.0** pin as Container Apps. Full Terraform validation reuses
the `CONTAINER_APPS_AZAPI_MIRROR` provider mirror. Missing tools or providers
are skips, not live validation.

Before adoption, rollback is removal of these sources and their test. After
adoption, index content, DNS records, locks and logs already sent to the
workspace are not undone by a source revert.
See [operator gates, rollback and sources](REFERENCE.md).
