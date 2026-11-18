# Azure Key Vault (opt-in)

One Key Vault that uses Azure RBAC and a `Key Vault Secrets User` grant for the
app's **existing** identity. Access policies are not used. The composition
creates no secrets and outputs no secret values. Choose **one** canonical
implementation: [Bicep](bicep/main.bicep) **or** [Terraform](terraform/main.tf),
never both over the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Reference `bicep/main.bicep` as a
resource-group-scoped module or `terraform` as a local Terraform child module.
The caller owns the resource group, identity, network, workspace, provider
authentication and state.

## What is included

| Part | Reason |
| --- | --- |
| Vault, `standard` SKU | The service itself. RBAC authorization and soft delete are declared explicitly. |
| `Key Vault Secrets User` role assignment | The app reads secret values through Entra ID; it cannot list keys, change secrets or grant access. |
| Private endpoint and DNS zone group | Only when `privateEndpoint` is supplied. |
| Public network access disabled | In every stage, unless a dev or test caller without a private endpoint sets `allowPublicNetworkAccess`; the firewall then denies all but `allowedIpRanges`. |
| `AuditEvent` diagnostic setting | Only when `logAnalyticsWorkspaceId` is supplied. |
| Staging and production purge protection | Deleted vaults and objects cannot be purged during the soft-delete period. It cannot be turned off again. |
| Production `CanNotDelete` lock | Toolkit production policy, scoped to the vault only. |
| Input guards | Reject unsafe staging and production inputs before deployment; they do not prove permissions or capacity. |

## Inputs

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Required | Meaning |
| --- | --- |
| `location` | Azure public-cloud region |
| `name` | 3–24 characters, globally unique; separate names per stage |
| `stage` | `dev`, `test`, `staging`, `prod` |
| `principalId` | Object (principal) ID of the existing app identity, **not** its client ID |
| `resource_group_id` | Terraform only: existing resource group ARM ID |

| Optional | Default | Meaning |
| --- | --- | --- |
| `privateEndpoint` | none | `subnetId` (a `Microsoft.Network/virtualNetworks/*/subnets/*` ARM ID) and `privateDnsZoneId` (the `privatelink.vaultcore.azure.net` zone ARM ID, exact casing) |
| `allowPublicNetworkAccess` | `false` | Dev or test without `privateEndpoint` only: keep the public endpoint with firewall default action `Deny` |
| `allowedIpRanges` | `[]` | IPv4 addresses or CIDR ranges the firewall allows; needs `allowPublicNetworkAccess` |
| `logAnalyticsWorkspaceId` | none | Existing workspace for `AuditEvent` logs; an empty string is rejected |

The subnet, the zone and its VNet link, and the workspace must already exist.

| Stage | Network | Purge protection | Diagnostics | Lock |
| --- | --- | --- | --- | --- |
| `dev`, `test` | Public access disabled; private endpoint optional, or opt in to a deny-by-default IP allow list | Off, so a deleted name can be purged and reused | Optional workspace | None |
| `staging` | **Private endpoint required**; public access disabled | **On** | **Workspace required** (`AuditEvent`) | None |
| `prod` | **Private endpoint required**; public access disabled | **On** | **Workspace required** (`AuditEvent`) | `CanNotDelete` |

Staging gets the production security guards so it rehearses the private path.
The `CanNotDelete` lock stays production-only: staging must stay easy to tear
down, and a lock adds no security control.

Outputs: vault resource ID and vault URI. The app reads secrets with the URI
and its managed identity, for example `azure-keyvault-secrets` with
`DefaultAzureCredential`, or with a Container Apps Key Vault secret reference.
Secret values are added out of band by a person or pipeline that holds
`Key Vault Secrets Officer`; this composition does not grant that role.

## Verify and adopt

From the repository root using installed tools:

```powershell
uv run --locked pytest tests\integration\delivery\infra\test_key_vault.py -m integration -q
```

The tests use the Bicep 0.39.26 / Terraform 1.11.3 baseline and the
**Azure/azapi 2.13.0** pin. Full Terraform validation reuses the
`CONTAINER_APPS_AZAPI_MIRROR` provider mirror. Missing tools or providers are
skips, not live validation.

Before adoption, rollback is removal of these sources and their test. After
adoption, purge protection, soft-deleted vaults, DNS records, locks and logs
already sent to the workspace are not undone by a source revert. Existing dev
and test vaults that relied on the old public default lose public access on the
next deployment; set `allowPublicNetworkAccess` with an allow list, or add a
private endpoint, before redeploying.
See [operator gates, rollback and sources](REFERENCE.md).
