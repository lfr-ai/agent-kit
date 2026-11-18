# Terraform state storage: operator gates, validation and sources

Start with the [consumer contract](README.md).

## Defaults this composition relies on

The sources declare only what differs from the platform default, plus
anonymous blob access pinned off. They deliberately **do not restate** these
2025-06-01 defaults: HTTPS-only traffic, disabled cross-tenant replication, the
`Hot` access tier, the `AzureServices` firewall bypass, and private container
access. `kind` and `sku` are required. `allowSharedKeyAccess: false` is declared
because an unset value allows Shared Key. `allowBlobPublicAccess: false` is
declared even though it matches the default, so a redeployment reverts anyone
enabling anonymous blob access on the state account. `minimumTlsVersion:
'TLS1_2'` is declared because an ARM or CLI deployment leaves it unset, which
permits TLS 1.0 and fails the common Azure Policy check. Versioning and both
soft-delete policies are off by default, and the retention period has no
default, so they are declared; one named value (`softDeleteRetentionDays`,
`soft_delete_retention_days` in Terraform, 30 days) sets both retention periods.

Because the other defaults are not declared, a source deployment does not revert
drift if someone changes them later, for example turning off HTTPS-only traffic
or enabling cross-tenant replication. Enforce them with the built-in Azure
Policy definitions for storage accounts or a post-deployment check.

## Operator gates and ownership

- Deploy this composition as an operator who can create role assignments,
  before any root module uses it (see the bootstrap order in the README). The
  CI identity needs only the container-scoped data role for state. It needs
  separate rights for the resources it manages.
- Pass the CI identity's **object (principal) ID**. The grant uses principal
  type `ServicePrincipal`, which covers app registrations with federated
  credentials and managed identities, and is named
  `guid(container ID, principal ID, role ID)` in both sources. Terraform
  computes the same UUIDv5 as Bicep, so the name matches when
  `resource_group_id` uses the canonical casing. `Reader` on the account is
  not needed unless a consumer sets `lookup_blob_endpoint`.
- Use one account per stage, so a development CI identity can never read or
  write production state. Use one `key` per root module.
- With Shared Key disabled, the portal, `az storage` (`--auth-mode login`) and
  Storage Explorer need Entra ID and a data role. Tools that only support
  account keys or SAS cannot access the state.
- Every state write creates a blob version. State files are small, but versions
  are kept until deleted. Add a lifecycle management rule for old versions if
  storage cost matters. Restore an earlier state by promoting a version, then
  run `terraform plan` before any apply.
- The production lock covers the account. It does **not** stop deleting or
  overwriting state blobs; versioning and soft delete cover that. It does not
  block updates or an actor who may remove locks. Terraform destroy removes its
  own lock first; operator approvals must deny unreviewed destroy, replacement
  and lock removal.
- Changing between `Standard_ZRS` and `Standard_GZRS` is a supported
  conversion. Moving between `Standard_LRS` and a zone-redundant SKU may need a
  conversion request or a migration; check the storage redundancy guidance.

## Network and logging trade-off

Without `privateEndpoint`, the account keeps the public endpoint but its
firewall uses `defaultAction: 'Deny'` with one `Allow` IP rule per
`allowedIpRanges` entry. Trusted Azure services keep the platform default
`bypass` (`AzureServices`), which is not restated. An empty list denies every
public client, so hosted runners with changing addresses cannot reach the
state. Storage IP rules accept public IPv4 only and reject `/31` and `/32`
prefixes; the sources reject non-IPv4 input before deployment, and operators
must pass a bare address instead of a `/32`.

With `privateEndpoint`, the sources add a blob private endpoint and a DNS zone
group, and declare `publicNetworkAccess: 'Disabled'`. Runners and operators
then need VNet access and resolution through the linked
`privatelink.blob.core.windows.net` zone. Passing `allowedIpRanges` together
with `privateEndpoint` is rejected, because those rules would never apply. The
endpoint stays optional in every stage, since it needs an existing network and
DNS zone before the first Terraform run.

Diagnostic settings would need a workspace, which is usually created by the
Terraform that depends on this account. Add them later from a separate,
reviewed change once the workspace exists. Azure Activity Log still records
control plane changes such as key settings and role assignments.

## Offline checks and pins

Checked tool baseline: **Bicep 0.39.26** and **Terraform 1.11.3**. Terraform
pins **Azure/azapi 2.13.0**. API versions: `Microsoft.Storage` 2025-06-01,
`Microsoft.Network` private endpoints 2025-01-01, role assignments 2022-04-01
and locks 2020-05-01. `Microsoft.Storage` 2025-06-01 is
the newest version in the local Bicep 0.39.26 type index. Azure/azapi 2.13.0
also knows 2025-08-01 and 2026-04-01, and the REST specifications publish newer
versions. Adopt one in both sources in a later reviewed change once Bicep knows
it.

The integration test relocates the exact source closure, then runs Bicep
format, lint, `build`, and `build-params` for the dev and prod examples. It
evaluates the exported guard with Bicep's parameter evaluator and runs the same
cases against the **unchanged variables.tf alone** with `terraform test`. Full
resource validation and the mocked plans in `terraform/tests` need the reviewed
Azure/azapi 2.13.0 mirror. Set `CONTAINER_APPS_AZAPI_MIRROR`; tests then run
`terraform init -backend=false -input=false -plugin-dir=<mirror>`. **No mirror
means a reported skip, not a provider-validation pass.** Mocks do not certify
ARM behavior, policies or permissions.

## Rollback

Before deployment, remove this directory, its integration test, its catalog
entry and the delivery README row; no cloud state has changed. After adoption,
migrate every consumer off the backend (`terraform init -migrate-state` to a new
backend) **before** deleting this account. State blobs, versions, soft-deleted
data and lock removals are not undone by a source revert. Re-enabling Shared
Key is a security regression; do not use it as a rollback shortcut. A Bicep
incremental deployment leaves a removed role assignment in place, so delete it
explicitly. Reverting the firewall change re-opens the public endpoint;
removing a private endpoint from the source does not delete it under Bicep
incremental mode. Never switch Bicep/Terraform ownership by applying the other
source; review import and state migration first.

## Sources

Checked on 2026-11-11:

- [azurerm backend](https://developer.hashicorp.com/terraform/language/backend/azurerm)
  (`use_azuread_auth`, OIDC, container-scoped `Storage Blob Data Contributor`)
  and [Store Terraform state in Azure Storage](https://learn.microsoft.com/en-us/azure/developer/terraform/store-state-in-azure-storage).
- [Prevent Shared Key authorization](https://learn.microsoft.com/en-us/azure/storage/common/shared-key-authorization-prevent)
  and [enforce a minimum TLS version](https://learn.microsoft.com/en-us/azure/storage/common/transport-layer-security-configure-minimum-version)
  (unset permits TLS 1.0).
- [Blob versioning](https://learn.microsoft.com/en-us/azure/storage/blobs/versioning-overview),
  [blob soft delete](https://learn.microsoft.com/en-us/azure/storage/blobs/soft-delete-blob-overview)
  and [container soft delete](https://learn.microsoft.com/en-us/azure/storage/blobs/soft-delete-container-overview).
- [Storage redundancy](https://learn.microsoft.com/en-us/azure/storage/common/storage-redundancy)
  and [change redundancy](https://learn.microsoft.com/en-us/azure/storage/common/redundancy-migration).
- [Storage account schema 2025-06-01](https://learn.microsoft.com/en-us/azure/templates/microsoft.storage/2025-06-01/storageaccounts),
  [role assignment schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2022-04-01/roleassignments)
  and [lock schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2020-05-01/locks).
