# Azure Cosmos DB for NoSQL (opt-in)

One Azure Cosmos DB for NoSQL account with **Microsoft Entra ID only**: local
(key) authentication is disabled, so no account key, resource token or
connection string exists in parameters, state or outputs. Optionally one
database with containers and one data-plane role assignment for an existing
identity. Choose **one** canonical implementation: [Bicep](bicep/main.bicep)
**or** [Terraform](terraform/main.tf), never both over the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Reference `bicep/main.bicep` as a
resource-group-scoped module or `terraform` as a local Terraform child module.
The caller owns the resource group, identities, network, workspace, provider
authentication and state.

## What is included

| Part | Reason |
| --- | --- |
| Account | NoSQL API (the default `GlobalDocumentDB` kind), single region, local authentication disabled, TLS 1.2 minimum. Only non-default settings are declared. |
| Database and containers | Only when `database` is supplied. Each container has one partition key path and uses large (version 2) partition keys. |
| Data-plane role assignment | Only when `principalId` is supplied: **Cosmos DB Built-in Data Contributor** (`00000000-0000-0000-0000-000000000002`) on the account. |
| Private endpoint and DNS zone group | Only when `privateEndpoint` is supplied. |
| Public network access disabled | In every stage, unless a dev or test caller without a private endpoint sets `allowPublicNetworkAccess`; the account then accepts only `allowedIpRanges`. |
| Diagnostic settings | Only when `logAnalyticsWorkspaceId` is supplied: `DataPlaneRequests`, `ControlPlaneRequests` and `Requests` metrics in resource-specific tables. |
| Production `CanNotDelete` lock | Toolkit production policy, scoped to the account only. |
| Input guards | Reject unsafe combinations before deployment; they do not prove permissions, quota or regional capacity. |

## Inputs

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Required | Meaning |
| --- | --- |
| `location` | Azure public-cloud region; production needs availability zones |
| `name` | Globally unique, 3–44 lowercase letters, digits or hyphens; distinct per stage |
| `stage` | `dev`, `test`, `staging`, `prod`; separate names/groups/state per stage |
| `resource_group_id` | Terraform only: existing resource group ARM ID |

Optional: `database` (none), `autoscaleMaxThroughput` (1000 RU/s),
`principalId` (no role assignment), `privateEndpoint` (none),
`allowPublicNetworkAccess` (`false`), `allowedIpRanges` (empty) and
`logAnalyticsWorkspaceId` (none, no diagnostics; an empty string is rejected).
`database` holds `name` and
an optional `containers` list of `name` and `partitionKeyPath` (for example
`/tenantId`). A partition key can't be changed after creation. `principalId` is
the identity's **object (principal) ID**, not its client ID. `privateEndpoint`
holds `subnetId` (a `Microsoft.Network/virtualNetworks/*/subnets/*` ARM ID) and
`privateDnsZoneId` (exact casing); both must exist already, and the
`privatelink.documents.azure.com` zone must be linked to the VNet.
`allowPublicNetworkAccess` is for dev or test without `privateEndpoint` only
and needs at least one IPv4 address or CIDR range in `allowedIpRanges`: Cosmos
DB treats an empty IP rule list as open to all networks.

| Stage | Capacity | Network | Resilience | Diagnostics | Lock |
| --- | --- | --- | --- | --- | --- |
| `dev`, `test` | **Serverless** (pay per request) | Public access disabled; private endpoint optional, or opt in to an IP allow list | Platform defaults: periodic backup, no zone redundancy | Optional workspace | None |
| `staging` | **Serverless** (pay per request) | **Private endpoint required**; public access disabled | Platform defaults: periodic backup, no zone redundancy | **Workspace required** | None |
| `prod` | **Provisioned autoscale** shared by the database, up to `autoscaleMaxThroughput` | **Private endpoint required**; public access disabled | **Zone redundant** and **continuous backup** (30-day point-in-time restore) | **Workspace required** | `CanNotDelete` |

Staging gets the production network and diagnostics guards so it rehearses the
private path. Provisioned capacity, zone redundancy, continuous backup and the
lock stay production-only: they are cost and resilience choices rather than
access controls, and serverless keeps an idle staging account cheap.

Capacity mode and the region's zone redundancy are chosen when the account is
created; changing them later is limited and at best one-way. Plan production as
its own account, not as a promoted dev account.

Outputs: account ID, `documentEndpoint`, database name (null when none) and
container names (Terraform sorts them; Bicep keeps input order).

## Connect the app with a managed identity

1. Pass the app's managed identity object ID as `principalId`, or ask the
   account owner to create the data-plane role assignment. Azure RBAC roles
   such as Contributor don't grant data access, and the data-plane role grants
   no management access.
2. The app uses the Cosmos DB SDK with a token credential (for example
   `DefaultAzureCredential`, or `ManagedIdentityCredential` with a
   user-assigned identity's *client* ID) and `documentEndpoint`. No key is
   available. This package adds no client dependency.
3. Create databases and containers through this module, not from the app: the
   built-in data roles don't allow management operations.

## Verify and adopt

From the repository root using installed tools:

```powershell
uv run --locked --no-sync pytest tests\integration\delivery\infra\test_cosmos_db.py -q
```

The tests use the Bicep 0.39.26 / Terraform 1.11.3 baseline and the
**Azure/azapi 2.13.0** pin. Full Terraform validation reuses the
`CONTAINER_APPS_AZAPI_MIRROR` provider mirror. Missing tools or providers are
skips, not live validation.

Before adoption, rollback is removal of these sources and their test. After
adoption, data, a deleted account, capacity mode, DNS records, locks and logs
already sent to the workspace are not undone by a source revert.
See [operator gates, rollback and sources](REFERENCE.md).
