# Key Vault: operator gates, validation and sources

Start with the [consumer contract](README.md).

## Defaults this composition relies on

From 2026-02-01, Azure RBAC authorization and soft delete (90-day retention) are
platform defaults. The sources still declare `enableRbacAuthorization: true` and
`enableSoftDelete: true`, so a redeployment reverts drift to access policies.
They do not restate the retention period or the disabled deployment,
template-deployment and disk-encryption access. `tenantId` and `sku` are
required by the API. `enablePurgeProtection` is declared only in staging and
production because it cannot be set back to `false`. `publicNetworkAccess` is
`Disabled` unless `allowPublicNetworkAccess` is set; the opt-in instead declares
`networkAcls` with default action `Deny` and the `allowedIpRanges` IP rules.
`enabled: true` is required on each diagnostic-setting log entry.

Enforce the RBAC permission model with the built-in Azure Policy definition as
well, so changes made outside this composition are caught between deployments.

## Operator gates and ownership

- The app identity already exists. Pass its **object (principal) ID**. The
  grant is `Key Vault Secrets User` on this vault only, with principal type
  `ServicePrincipal` (managed identities included). Its name is
  `guid(vault ID, principal ID, role ID)` in both sources. Terraform computes
  the same UUIDv5 as Bicep, so the name matches when `resource_group_id` uses
  the canonical casing. Role assignments can take several minutes to apply.
- The deploying identity needs `Microsoft.Authorization/roleAssignments/write`
  on the vault, for example `Role Based Access Control Administrator`
  constrained to these roles. Whoever writes secret values needs
  `Key Vault Secrets Officer`, granted outside this composition.
- The vault uses the deployment's tenant: `tenant()` in Bicep and the
  authenticated `azapi_client_config` tenant in Terraform. The app identity
  must belong to the same tenant.
- For a private endpoint, provide an existing same-region subnet and an existing
  `privatelink.vaultcore.azure.net` zone with a VNet link. The app keeps using
  the public vault URI, which resolves to the private address. A Container Apps
  environment reaches a private vault only when it is VNet-integrated and
  resolves that zone. Trusted Azure services can still reach the vault when
  public access is disabled. Without a private endpoint and without
  `allowPublicNetworkAccess`, the vault is reachable only by trusted services:
  dev and test callers must choose one of the two.
- Vault names are global. A deleted vault stays soft-deleted for 90 days and
  holds its name. In dev and test, purge it (needs the purge permission) or
  recover it before reusing the name. In staging and production purge
  protection prevents purging, so a deleted name is unavailable for the full
  period.
- The production lock covers the vault and is inherited by its role assignment.
  It does **not** stop data-plane deletion of secrets; soft delete and purge
  protection cover that. It also does not block updates or an actor who may
  remove locks. Terraform destroy removes its own lock first; operator
  approvals must deny unreviewed destroy, replacement and lock removal.
- Diagnostics need an existing Log Analytics workspace (required in
  production), which may sit in another subscription. `AuditEvent` records
  authenticated REST requests, including failed ones. Log ingestion
  and retention are billed by the workspace. Delete the diagnostic setting
  before deleting or re-creating the vault: Azure Monitor can reapply leftover
  settings to a re-created resource with the same ID.
- The guards accept only the Azure public-cloud private DNS zone.

## Offline checks and pins

Checked tool baseline: **Bicep 0.39.26** and **Terraform 1.11.3**. Terraform
pins **Azure/azapi 2.13.0**. API versions: `Microsoft.KeyVault/vaults`
2026-02-01, role assignments 2022-04-01, `Microsoft.Network` 2025-01-01, locks
2020-05-01 and `Microsoft.Insights/diagnosticSettings` 2021-05-01-preview (the
version AVM and the Container Apps composition use).

Key Vault control-plane API versions before 2026-02-01 retire on 2027-02-27,
and 2026-02-01 is the first with the RBAC default. It is in the Azure/azapi
2.13.0 schema but newer than the Bicep 0.39.26 type index. Bicep therefore
suppresses `BCP081` on that one line and does not type-check the vault
properties; the Terraform embedded schema validation and the tests cover them.
The REST specifications also publish 2026-05-15, which neither tool knows yet:
adopt it in a later reviewed change.

The integration test relocates the exact source closure, then runs Bicep
format, lint, `build`, and `build-params` for the dev and prod examples. It
evaluates the exported guards with Bicep's parameter evaluator and runs the
same cases against the **unchanged variables.tf alone** with `terraform test`.
Full resource validation and the mocked plans in `terraform/tests` need the
reviewed Azure/azapi 2.13.0 mirror. Set `CONTAINER_APPS_AZAPI_MIRROR`; tests
then run `terraform init -backend=false -input=false -plugin-dir=<mirror>`.
**No mirror means a reported skip, not a provider-validation pass.** Mocks do
not certify ARM behavior, policies or permissions.

## Rollback

Before deployment, remove this directory, its integration test, its catalog
entry and the delivery README row; no cloud state has changed. After adoption,
revert inputs through the owning IaC tool and review the plan. Purge protection
cannot be disabled, soft-deleted vaults keep their name for 90 days, and
secrets, DNS records, removed grants and lock removals are not undone by a
source revert. A Bicep incremental deployment leaves a removed role assignment
or diagnostic setting in place, so delete it explicitly. Logs already ingested
stay in the workspace for its retention period. Never switch Bicep/Terraform
ownership by applying the other source; review import and state migration
first.

## Sources

Checked on 2026-11-11:

- [Azure RBAC is the default access model from API 2026-02-01](https://learn.microsoft.com/en-us/azure/key-vault/general/access-control-default)
  and [Key Vault RBAC guide and built-in roles](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide).
- [Soft delete](https://learn.microsoft.com/en-us/azure/key-vault/general/soft-delete-overview)
  and [Key Vault security best practices](https://learn.microsoft.com/en-us/azure/key-vault/general/secure-key-vault).
- [Private Link for Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/general/private-link-service)
  and [private endpoint DNS zone values](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns).
- [Key Vault logging](https://learn.microsoft.com/en-us/azure/key-vault/general/logging)
  (`AuditEvent`).
- [Key Vault REST specification](https://github.com/Azure/azure-rest-api-specs/tree/main/specification/keyvault/resource-manager/Microsoft.KeyVault/KeyVault/stable)
  (2026-02-01 and 2026-05-15 property defaults).
- [Role assignment schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2022-04-01/roleassignments),
  [Bicep guid()](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/bicep-functions-string#guid),
  [private endpoint schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2025-01-01/privateendpoints)
  and [lock schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2020-05-01/locks).
- [azapi_client_config](https://registry.terraform.io/providers/Azure/azapi/latest/docs/data-sources/client_config).
