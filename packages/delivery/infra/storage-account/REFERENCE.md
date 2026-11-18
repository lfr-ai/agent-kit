# Storage account: operator gates, evidence and rollback

Start with the [module contract](README.md).

## Security and defaults

`allowSharedKeyAccess: false` rejects account-key authorization and account/service
SAS for blobs. Entra-authorized **user delegation SAS remains possible**; this
module does not issue one. `defaultToOAuthAuthentication: true` selects OAuth by
default in the portal but is not the enforcement mechanism. Account-level
`allowBlobPublicAccess: false` explicitly denies anonymous blob reads, including
if a caller later changes a container's access setting.

The pinned Storage API defaults to HTTPS-only and disallows cross-tenant
replication for new accounts. Platform-managed encryption is retained. The Hot
tier and private container defaults are not restated. TLS 1.2 is explicit rather
than relying on the API's documented unset minimum. The account-level anonymous
access denial is intentionally explicit despite its secure platform default.
Omitted defaults are not a drift-remediation guarantee; enforce organizational
requirements with Azure Policy and post-deployment checks.

Production uses ZRS, not geo-replication. Confirm ZRS availability in the chosen
region. Versioning and 30-day soft deletion protect against some overwrites and
deletions, **not account deletion or regional disaster**. Previous versions can
accumulate indefinitely: 30 days (the `softDeleteRetentionDays` value,
`soft_delete_retention_days` in Terraform) is the soft-delete period, not a lifecycle rule
that purges versions after 30 days. Storage versions, soft-deleted data, private
endpoints and workspace ingestion/retention incur costs. Choose workload-specific
lifecycle and backup policies separately; none are silently added here.

## Ownership and operator checks

- Keep one IaC owner. Terraform has no backend, provider configuration, data
  sources or account discovery; the caller explicitly supplies authentication,
  subscription, resource group and state. Bicep runs at resource-group scope.
  Never apply the other implementation to resources already owned by one tool
  without reviewed import/state migration.
- Use synthetic dev/prod examples only for compilation. Replace all example
  names, region and zero-GUID resource IDs with reviewed operator inputs.
- Shared Bicep/Terraform guards require the staging and production
  network/workspace inputs, a subnet-shaped ARM ID and the Azure public-cloud
  blob DNS zone ARM ID (exact casing). They do not prove
  resource existence, private endpoint approval, VNet links, DNS
  resolution or authorization. Bicep types/decorators check name lengths and
  stages; ARM checks naming syntax and uniqueness. Terraform additionally rejects
  malformed account/container names and duplicate container entries locally.
- The runtime identity already exists. Pass its **object (principal) ID**. The
  module grants it **Storage Blob Data Contributor**
  (`ba92f5b4-2d11-453d-a403-e96b0029c9fe`) with principal type
  `ServicePrincipal` (managed identities included) on each managed container,
  or on the account when `containers` is empty. Each name is
  `guid(scope ID, principal ID, role ID)` in both sources; Terraform computes
  the same UUIDv5 as Bicep, so names match when `resource_group_id` uses the
  canonical casing. The offline test checks that parity for the synthetic
  inputs. Role assignments can take several minutes to apply. Grant read-only
  consumers **Storage Blob Data Reader** through their owner, outside this
  module. No other principal, credential or connection string is created here.
  Shared-key-dependent clients must migrate to Entra before adoption.
- Adding the first container, or removing the last one, **moves** the grant:
  the account-scoped assignment is replaced by container-scoped ones (or the
  reverse). Review that plan; in production the removed assignment sits under
  the inherited lock (see below).
- Private endpoints alone do not close public access. Both sources disable
  public network access in every stage unless a dev or test caller without a
  private endpoint sets `allowPublicNetworkAccess`; that opt-in declares
  `networkAcls` with default action `Deny` plus the `allowedIpRanges` rules.
  Existing dev/test accounts that relied on the old public default lose public
  access on the next deployment. Only the
  `blob` subresource and its DNS group are created; clients needing DFS, Files,
  Queue or Table need a separately reviewed composition.
- The deployer needs rights to create storage resources, join the supplied subnet,
  connect the DNS zone, configure diagnostics with the workspace, write locks,
  and `Microsoft.Authorization/roleAssignments/write` on the account (for
  example `Role Based Access Control Administrator` constrained to Storage Blob
  Data Contributor).
  Cross-subscription network/workspace permissions and resource-provider
  registration remain operator checks; no automatic registration/login is run.
- Diagnostics are scoped to `blobServices/default`, not the account. Verify
  actual reads/writes/deletes reach the workspace after deployment; mocked plans
  cannot demonstrate ingestion.
- `CanNotDelete` is scoped to the storage account and inherited by its ARM
  children. It does **not** prevent data-plane blob deletion or updates.
  An authorized actor can remove it. The Terraform lock explicitly depends on
  the managed blob service, containers, Blob Data Contributor assignments and
  diagnostics: creation puts the lock last, and reverse destroy removes it
  before those children and the account.
  Approval/policy must still reject unreviewed destruction. For existing
  deployments, review/apply this dependency-only update through the owning
  workflow so state records the relationships before a later full destroy;
  new source alone is not evidence that older state has been updated.

### Removing children while retaining the account

`depends_on` does not unlock an unchanged lock when only a container, a role
assignment or another child is removed/replaced. That operation can still fail
with `ScopeLocked`.
Use a **separately approved maintenance/unlock sequence**, not an automatic retry:

1. Approve the exact child removals/replacements, data recovery plan and unlock
   window. Freeze concurrent applies and check for other inherited locks.
   This module cannot remove locks owned by a resource group or another owner.
2. In the consumer's reviewed copy, temporarily set only
   `azapi_resource.protection.count` to `0`. Keep `stage = "prod"` and all child
   inputs unchanged. Review a separate plan that removes **only this lock**,
   then obtain approval to apply it through the owning workflow. Do not remove
   resources from state, change stage to bypass guards or delete the module.
3. Keep that temporary lock change in place while making the approved child
   edits. Review and separately approve the child plan; reject account deletion
   or replacement and unrelated changes. Apply only after confirming the lock
   is absent. Required production diagnostics must be restored/replaced within
   the approved maintenance window, not silently dropped from the contract.
4. Restore the original production lock condition in a final reviewed change.
   With the intended children present and no pending child removals, approve a
   plan that recreates the account-scoped `CanNotDelete` lock. Verify the lock
   and a clean follow-up plan before releasing the automation freeze. If a
   step fails, stop and reassess recovery/relocking; do not blindly retry.

These are operator instructions, not commands executed by this repair. The
offline dependency check does not authorize or certify a live teardown.

## Offline evidence and limitations

The integration test copies byte-identical sources away from the checkout.
Installed Bicep **0.39.26** checks format, lint, build and parameter compilation.
Exported production guards are evaluated with both accepted and rejected inputs;
mutated production examples must fail. Compiled ARM assertions check private
network conditions, blob diagnostics and resource-scoped locks.

Installed Terraform **1.11.3** checks formatting and runs input-contract tests
against the unchanged `variables.tf` without a provider. Full `validate` and the
six `terraform test` runs require the existing local **Azure/azapi 2.13.0**
mirror named by `CONTAINER_APPS_AZAPI_MIRROR`. Initialization uses
`-backend=false -input=false -get=false -plugin-dir=<mirror>` only in the
temporary copy; provider downloads, backend access and account discovery are
not permitted. All resource tests use `mock_provider "azapi"` and `command = plan`.
No test applies resources. Missing tools/mirror produce explicit skips.
Mocked plans override the account/container IDs during plan
(`override_during = plan`) with synthetic ARM IDs, so they assert the exact
role-assignment names, scope, role GUID, principal and principal type; Bicep's
`guid()` is evaluated offline for the same inputs and must produce those names.

An additional native `terraform graph` regression checks that the lock has
dependency paths to the account and **every managed protected child**. This
proves the configuration ordering needed for reverse destroy, independently of
mocked-plan values. It does not execute destruction, inspect live state or prove
Azure lock propagation. Mocked plans alone do not prove lifecycle ordering.

API pins remain:

| Resources | API version |
| --- | --- |
| Storage account, blob service, containers | `2025-06-01` |
| Private endpoint and DNS zone group | `2025-01-01` |
| Diagnostic setting | `2021-05-01-preview` |
| Resource lock | `2020-05-01` |
| Role assignments | `2022-04-01` |

These are offline source/schema/mocked-plan checks, not Azure service
certification. Account-name availability, regional features, live API behavior,
Azure Policy, RBAC propagation, DNS, restore procedures and diagnostic ingestion
require an explicitly authorized operator session later.

## Rollback

This repair performs no deployment and changes no cloud or Terraform state.
Reverting the lock dependency fix reintroduces the child-deletion race; it is
not a safe operational rollback. Relock through the approved sequence above
if a maintenance change must be abandoned.
To undo the repair, revert its added variables/docs/tests and the storage entries
in `COMPOSITIONS` and `AZURE_COMPOSITIONS`, and restore the prior conditional in
`terraform/main.tf`; regenerate the delivery catalog from the reviewed owning
sources. Retain the pre-existing storage Bicep/Terraform sources. That exact
revert deliberately restores the original unregistered,
incomplete-module gate failure rather than hiding or deleting unfinished work.

After adoption, revert inputs through the owning IaC tool and review its plan.
Reverting the runtime-identity grant (removing `principalId` and both
role-assignment resources) makes Terraform delete the assignments, so the app
loses blob access until an operator re-grants it; production first needs the
unlock sequence above. Bicep incremental mode leaves removed assignments in
place, so delete them explicitly if intended. Callers must restore the
`principalId` input when re-applying this version.
Do not delete the module from state or switch implementations as a rollback.
Resource removal in Bicep incremental mode does not delete the live endpoint,
diagnostics, containers or lock. Terraform removal/destroy can delete them and
the account; the managed lock is not a substitute for approval.

Source reverts do not recover permanently deleted blobs, containers or accounts,
undo DNS changes, remove ingested logs or restore lost Terraform state.
Disabling versioning does not delete existing versions; soft-deleted objects
remain recoverable only for their applicable retention window. Restore data
explicitly and rehearse that procedure before relying on it. Removing production
settings from a source does not prove that the service reset them; inspect the
reviewed plan and resulting configuration.

## Official sources

Reviewed on 2026-11-12 (public Azure documentation only):

- [Storage account API and defaults](https://learn.microsoft.com/en-us/azure/templates/microsoft.storage/2025-06-01/storageaccounts)
  and [blob containers](https://learn.microsoft.com/en-us/azure/templates/microsoft.storage/2025-06-01/storageaccounts/blobservices/containers).
- [Prevent Shared Key authorization](https://learn.microsoft.com/en-us/azure/storage/common/shared-key-authorization-prevent)
  and [identity-based authorization guidance](https://learn.microsoft.com/en-us/azure/storage/common/storage-account-keys-manage).
- [Storage private endpoints and DNS](https://learn.microsoft.com/en-us/azure/storage/common/storage-private-endpoints).
- [Blob monitoring reference](https://learn.microsoft.com/en-us/azure/storage/blobs/monitor-blob-storage-reference).
- [Blob versioning](https://learn.microsoft.com/en-us/azure/storage/blobs/versioning-overview),
  [blob soft deletion](https://learn.microsoft.com/en-us/azure/storage/blobs/soft-delete-blob-overview)
  and [container soft deletion](https://learn.microsoft.com/en-us/azure/storage/blobs/soft-delete-container-overview).
- [Resource locks and data-plane limitations](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/lock-resources).
- [Role assignment schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2022-04-01/roleassignments)
  and [Storage Blob Data Contributor](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/storage#storage-blob-data-contributor).
