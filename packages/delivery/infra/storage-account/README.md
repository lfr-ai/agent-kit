# Azure Storage account for blobs (opt-in)

One general-purpose v2 storage account with **Microsoft Entra ID authorization**:
shared key authorization and anonymous blob access are disabled. No keys,
connection strings or SAS tokens are read or output. Choose **one** implementation:
[Bicep](bicep/main.bicep) **or** [Terraform](terraform/main.tf), never both over
the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Use `bicep/main.bicep` as a resource-group-scoped
module or `terraform` as a local child module. The caller owns the resource group,
the existing runtime identity, any further data-plane role assignments, existing
network and workspace, provider authentication, subscription selection and
Terraform state.

The module grants the runtime identity (`principalId`) **Storage Blob Data
Contributor** with principal type `ServicePrincipal` on **each managed
container**, or on the **account** when `containers` is empty. Read-only
consumers must be granted **Storage Blob Data Reader** by their owner, outside
this module.

## Contract

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Input | Meaning |
| --- | --- |
| `location` | Required Azure public-cloud region; production needs ZRS support |
| `name` | Required globally unique account name: 3–24 lowercase letters/digits; distinct per stage |
| `stage` | Required `dev`, `test`, `staging` or `prod`; never inferred from a workspace |
| `resource_group_id` | Terraform only: required existing resource group ARM ID |
| `principalId` | Required object (principal) ID of the existing runtime identity, **not** its client ID; exactly 36 characters |
| `containers` | Optional list, default empty; unique private container names, 3–63 lowercase letters/digits/single hyphens, starting and ending alphanumeric |
| `privateEndpoint` | Optional object with `subnetId` (a `Microsoft.Network/virtualNetworks/*/subnets/*` ARM ID) and `privateDnsZoneId` (the blob zone ARM ID, exact casing); required in staging and production |
| `allowPublicNetworkAccess` | Optional bool, default `false`; dev or test without `privateEndpoint` only. Keeps the public endpoint with firewall default action `Deny` |
| `allowedIpRanges` | Optional list, default empty; public IPv4 addresses or CIDR ranges the firewall allows. Needs `allowPublicNetworkAccess`. Storage rejects private ranges and `/31`–`/32` prefixes: pass a bare address instead |
| `logAnalyticsWorkspaceId` | Optional existing workspace ARM ID, default none; an empty string is rejected; required in staging and production |

Supply an existing same-region subnet and an existing
`privatelink.blob.core.windows.net` private DNS zone already linked to the client
VNet. This module creates the private endpoint and its DNS zone group, **not**
the subnet, DNS zone or VNet link. Networking supports the blob endpoint only.

| Stage | Replication | Network | Data protection | Diagnostics | Lock |
| --- | --- | --- | --- | --- | --- |
| `dev`, `test` | `Standard_LRS` | Public access disabled; private endpoint optional, or opt in to a deny-by-default IP allow list | Platform defaults (off) | Optional workspace | None |
| `staging` | `Standard_LRS` | Private endpoint required, public access disabled | Platform defaults (off) | Workspace required | None |
| `prod` | `Standard_ZRS` | Private endpoint required, public access disabled | Versioning plus 30-day blob/container soft deletion | Workspace required | Account-scoped `CanNotDelete` |

Public network access is disabled in **every** stage unless a dev or test
caller opts in. Staging gets the production network and diagnostics guards so
it rehearses the private path. ZRS, versioning, soft deletion and the lock stay
production-only: they are availability, recovery and cost choices rather than
access controls, and staging data is disposable.
Diagnostics target the **blob service**: `StorageRead`, `StorageWrite`,
`StorageDelete` and `Transaction` metrics. All accounts require TLS 1.2 and
default the portal authentication choice to OAuth. HTTPS-only and platform
encryption defaults are retained.

Outputs are `storageAccountId`, `blobEndpoint`, and `containerNames` (snake_case
in Terraform). Container output ordering is not a cross-tool contract.

## Adoption

- The runtime identity receives **Storage Blob Data Contributor** from this
  module at the narrowest scope it owns (each managed container, else the
  account). Grant read-only consumers **Storage Blob Data Reader** through
  their owner at the narrowest container/account scope. Management-plane
  Contributor alone does not grant blob data access. Use a managed identity or
  explicitly configured federation, not an account key. No identity or account
  context is selected automatically.
- Private clients, including CI jobs that access blobs, need VNet reachability
  and private DNS. Standard hosted runners have no implicit access.
- This is application blob storage, not the sibling Terraform-state composition.
  It does not configure Files, Queue, Table, static websites, hierarchical
  namespace, lifecycle deletion, backups, customer-managed keys, or role
  assignments beyond the runtime identity's grant.
- Review the deployment and state with the selected owning tool before adoption.
  Inputs are not evidence of resource existence, permissions, DNS or capacity.

## Offline verification

From the repository root with installed tools and the existing Python environment:

```powershell
uv run --locked --no-sync pytest tests/integration/delivery/infra/test_storage_account.py -q
task verify -- delivery
```

Tests relocate the complete source closure into temporary directories. They run
Bicep formatting, lint, compilation, dev/prod examples and negative production
guards; Terraform formatting, provider-free input tests, and cached-provider
schema validation plus **mocked plans only**. Set `CONTAINER_APPS_AZAPI_MIRROR`
to an existing local Azure/azapi 2.13.0 mirror to enable the full Terraform check.
Missing tools or a missing mirror are reported skips, not validation passes.
Tests do not download providers or use Azure account context.

Tool baseline: Bicep **0.39.26**, Terraform **1.11.3**; provider pin:
**Azure/azapi 2.13.0**. Role assignments use API **2022-04-01**.
[REFERENCE.md](REFERENCE.md) records API pins, official
sources, limits, costs, operator checks and rollback. A source revert cannot
recover deleted data or undo existing infrastructure/state.
