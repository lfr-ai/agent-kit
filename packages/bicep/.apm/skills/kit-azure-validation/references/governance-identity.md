# Governance and identity

## Managed identities

- Give workloads a managed identity instead of secrets. Use a user-assigned
  identity when several resources share it or when its lifecycle must outlive
  a single resource; use system-assigned when the identity belongs to exactly
  one resource.
- Disable key-based access where the service supports Entra ID
  (`allowSharedKeyAccess: false` on storage, RBAC authorization on Key Vault,
  local authentication disabled on messaging and AI services).

## Role assignments

- Grant the narrowest built-in data-plane role at the narrowest scope (one
  storage account rather than the resource group). Avoid `Owner`,
  `Contributor`, and `User Access Administrator` for workloads.
- Name role assignments deterministically with
  `guid(scope, principalId, roleDefinitionId)` so repeated deployments are
  idempotent.
- Set `principalType` for newly created principals to avoid replication-delay
  failures.
- Any what-if change to `Microsoft.Authorization/roleAssignments`,
  `roleDefinitions`, or identity settings is an access change: list the
  principal, role, and scope in review evidence even when it is a `Create`.

## Pipeline identity with OIDC

- Authenticate CI with workload identity federation: an Entra ID application
  or user-assigned identity with a federated credential whose subject names
  the GitHub environment (`repo:<owner>/<repo>:environment:<name>`). No client
  secret is stored.
- Use separate identities for preview (Reader on the scope) and deploy
  (only the roles the template needs). Deploy identities that create role
  assignments need `Role Based Access Control Administrator` with a condition
  restricting assignable roles, not `Owner`.
- Bind the deploy identity's federated credential to a protected environment
  with required reviewers.

## Azure Policy

- Assign policy at management group or subscription scope for guardrails
  that templates must not be able to bypass: allowed locations, allowed SKUs,
  required tags, denial of public network access, diagnostic settings.
- Policy with `deny` effect fails a deployment at validation; `audit` and
  `auditIfNotExists` report later; `modify` and `deployIfNotExists` remediate.
  Read policy results in `az deployment group validate` output before
  blaming the template.
- Manage policy definitions and assignments as code with what-if review like
  any other deployment; exemptions need an owner, reason, and expiry.

## Locks

- Use `CanNotDelete` resource locks or stack deny settings on stateful
  production resources. Locks also block some management operations (for
  example listing storage keys with a `ReadOnly` lock); test before applying
  `ReadOnly`.

## Review checklist

- [ ] Workloads authenticate with managed identities; key access disabled.
- [ ] Role assignments are least privilege, narrowly scoped, and named with
      `guid()`.
- [ ] CI uses OIDC with environment-bound subjects and split identities.
- [ ] Guardrails live in policy assignments above the workload scope.
- [ ] Stateful production resources carry locks or deny settings.

## Sources

- <https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview>
- <https://learn.microsoft.com/azure/role-based-access-control/best-practices>
- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/scenarios-rbac>
- <https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect>
- <https://learn.microsoft.com/entra/workload-id/workload-identity-federation>
- <https://learn.microsoft.com/azure/governance/policy/overview>
- <https://learn.microsoft.com/azure/azure-resource-manager/management/lock-resources>
