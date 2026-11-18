# Azure Managed Redis (opt-in)

One Azure Managed Redis cache, one database and a data-access grant for the
app's **existing** managed identity. Authentication is Entra ID only; access
keys stay at their disabled default and no key or secret is read or output.
Choose **one** canonical implementation: [Bicep](bicep/main.bicep) **or**
[Terraform](terraform/main.tf), never both over the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Reference `bicep/main.bicep` as a
resource-group-scoped module or `terraform` as a local Terraform child module.
The caller owns the resource group, identity, network, provider authentication
and state.

## What is included

| Part | Reason |
| --- | --- |
| Cache and `default` database | The service itself. Only non-default settings are declared, plus access keys disabled explicitly. |
| Access policy assignment | Gives the existing app identity the built-in `default` data policy; no keys. |
| Private endpoint and DNS zone group | Only when `privateEndpoint` is supplied. |
| Public network access disabled | In every stage, unless a dev or test caller without a private endpoint sets `allowPublicNetworkAccess`. Azure Managed Redis has no IP firewall, so the opt-in is all-or-nothing; Entra ID still guards data access. |
| Diagnostic settings | Only when `logAnalyticsWorkspaceId` is supplied: cluster `AllMetrics` and database `ConnectionEvents` logs to that workspace. |
| Production `CanNotDelete` lock | Toolkit production policy, scoped to the cache only. |
| Input guards | Reject unsafe combinations before deployment; they do not prove permissions or capacity. |

The database uses `EnterpriseCluster`: one endpoint that a plain, non-cluster
Redis client can use. The trade-off is lower scale-out throughput than
`OSSCluster`, and multi-key commands must keep keys in one hash slot (use
`{hash tags}`). The policy is a create-time choice, so pick it before adoption.

## Inputs

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Required | Meaning |
| --- | --- |
| `location` | Azure public-cloud region |
| `name` | 2–32 lowercase letters/digits/single hyphens; start with letter, end alphanumeric |
| `stage` | `dev`, `test`, `staging`, `prod`; separate names/groups/state per stage |
| `principalId` | Object (principal) ID of the existing app identity, **not** its client ID |
| `resource_group_id` | Terraform only: existing resource group ARM ID |

Optional: `sku` (`Balanced_B0`), `privateEndpoint` (none),
`allowPublicNetworkAccess` (`false`; dev or test without `privateEndpoint` only)
and `logAnalyticsWorkspaceId` (none, no diagnostics; an empty string is
rejected). `privateEndpoint` holds
`subnetId` (a `Microsoft.Network/virtualNetworks/*/subnets/*` ARM ID) and
`privateDnsZoneId`. Both must exist already, and the
`privatelink.redis.azure.net` zone must be linked to the VNet. The workspace
must already exist; pass its ARM ID in canonical casing
(`/subscriptions/…/resourceGroups/…/providers/Microsoft.OperationalInsights/workspaces/…`).

| Stage | Network | SKU | Diagnostics | Lock |
| --- | --- | --- | --- | --- |
| `dev`, `test` | Public access disabled; private endpoint optional, or opt in to the public endpoint (Entra ID only) | Any Managed Redis SKU | Optional workspace | None |
| `staging` | **Private endpoint required**; public access disabled | Any Managed Redis SKU | **Workspace required** | None |
| `prod` | **Private endpoint required**; public access disabled | **Not `Balanced_B0` or `Balanced_B1`**; `Balanced_B3` or larger | **Workspace required** | `CanNotDelete` |

Staging gets the production network and diagnostics guards so it rehearses the
private path. The SKU floor and lock stay production-only: they are cost and
availability choices, not security controls, and a small staging cache keeps
cost down.

Outputs: resource ID, host name and port (`10000`). Connect over TLS with an
Entra ID token for the identity, for example `redis-py` with the
`redis-entraid` managed-identity credential provider. Use a user-assigned
identity with its *client* ID and a non-cluster `Redis` client with `ssl=True`.
This package adds no client dependency.

## Verify and adopt

From the repository root using installed tools:

```powershell
uv run --locked pytest tests\integration\delivery\infra\test_managed_redis.py -q
```

The tests use the same Bicep 0.39.26 / Terraform 1.11.3 baseline and
**Azure/azapi 2.13.0** pin as Container Apps. Full Terraform validation reuses
the `CONTAINER_APPS_AZAPI_MIRROR` provider mirror. Missing tools or providers
are skips, not live validation.

Before adoption, rollback is removal of these sources and their test. After
adoption, cache data, DNS records, locks and logs already sent to the workspace
are not undone by a source revert. Existing dev and test caches that relied on
the old public default lose public access on the next deployment; set
`allowPublicNetworkAccess` or add a private endpoint first.
See [operator gates, rollback and sources](REFERENCE.md).
