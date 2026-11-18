# Container Registry: operator gates, validation and sources

Start with the [consumer contract](README.md).

## Defaults this composition relies on

The sources declare only what differs from the platform default, with one
security exception: `adminUserEnabled: false` and `anonymousPullEnabled: false`
are declared so the Entra-only claim is part of the source and its tests. They
deliberately **do not restate** these 2025-11-01 defaults: the trusted-services
network bypass (needed by
`az acr import` into a private registry), the `LegacyRegistryPermissions` role
mode (so `AcrPull` and `AcrPush` apply), and the retention period of 7 days.
Zone redundancy is automatic for every SKU in regions with availability zones.
The legacy `zoneRedundancy` property no longer controls it and may still read
`Disabled`, so it is not set. `publicNetworkAccess` is declared to disable
public access unless a dev or test caller sets `allowPublicNetworkAccess`.
Basic and Standard cannot disable public access or hold IP rules, so they need
that opt-in; Premium with the opt-in declares a `networkRuleSet` with
`defaultAction: Deny` and the `allowedIpRanges`. `enabled: true` is required on each
diagnostic-setting log entry.

A redeployment turns the admin user and anonymous pull off again, but only
when it runs. Enforce them between deployments with the built-in Azure Policy
definitions for container registries or a post-deployment check on
`adminUserEnabled` and `anonymousPullEnabled`.

## Operator gates and ownership

- The identities already exist. Pass **object (principal) IDs**. Each grant is
  scoped to this registry, uses principal type `ServicePrincipal` (managed
  identities included) and is named `guid(registry ID, principal ID, role ID)`
  in both sources. Terraform computes the same UUIDv5 as Bicep, so the names
  match when `resource_group_id` uses the canonical casing.
- The deploying identity needs `Microsoft.Authorization/roleAssignments/write`
  on the registry, for example `Role Based Access Control Administrator`
  constrained to these roles.
- Private endpoints need Premium. The endpoint uses one private IP address for
  the registry and one for its regional data endpoint, which Azure enables
  automatically. Provide an existing same-region subnet and an existing
  `privatelink.azurecr.io` zone with a VNet link. A Container Apps environment
  pulls from a private registry only when it is VNet-integrated and resolves
  that zone. With public access disabled, the portal and CLI cannot list
  repositories from outside the VNet.
- **Untagged-manifest retention is a Premium preview feature.** Deletion is
  unrecoverable. Microsoft warns against it for systems that pull by digest,
  which Container Apps does here. It is safe only when every deployed digest
  keeps a unique tag that is never moved or removed, for example one tag per
  build. Lock a deployed image with
  `az acr repository update --image app@sha256:… --delete-enabled false` to
  exclude it. Retention covers Docker media types only, not OCI manifests, and
  only manifests untagged after it was enabled. Disable it with
  `az acr config retention update --status disabled --type UntaggedManifests`
  if that tag rule cannot be guaranteed.
- The production lock covers the registry and is inherited by its role
  assignments. It does **not** stop deleting images or repositories; use image
  locks for that. It does not block updates or an actor who may remove locks.
  Terraform destroy removes its own lock first; operator approvals must deny
  unreviewed destroy, replacement and lock removal.
- Diagnostics need an existing Log Analytics workspace (required in
  production), which may sit in another subscription. Login and repository
  events (push, pull, delete) are billed by the workspace. Delete the
  diagnostic setting before deleting or re-creating the registry: Azure Monitor
  can reapply leftover settings to a re-created resource with the same ID.
- Moving between Basic, Standard and Premium is an in-place update. Remove the
  private endpoint and retention policy before leaving Premium.
- The guards accept only the Azure public-cloud private DNS zone, by exact ARM
  ID shape and casing, and a `Microsoft.Network/virtualNetworks/*/subnets/*`
  subnet ID.

## Hosted CI trade-off

| Option | Security | Effort | Decision |
| --- | --- | --- | --- |
| Promote with `az acr import` from the test registry | Production data plane stays private; the exact tested digest moves inside Azure | One extra pipeline step and role | **Default** |
| CI inside the VNet (self-hosted, GitHub larger runners with Azure private networking, Managed DevOps Pools) | Private; CI pushes directly | Runner infrastructure and network to operate | Supported: pass `pushPrincipalId` |
| Public access with an IP allowlist for hosted runners | Hosted runner ranges are large, shared and change; the data plane is reachable from the internet | Allowlist upkeep | Not offered in production |

Dev and test keep public access with Entra ID only when the caller sets
`allowPublicNetworkAccess`, so hosted CI pushes there without network work.
On Premium, add the runner or office ranges to `allowedIpRanges`.

## Offline checks and pins

Checked tool baseline: **Bicep 0.39.26** and **Terraform 1.11.3**. Terraform
pins **Azure/azapi 2.13.0**. API versions:
`Microsoft.ContainerRegistry/registries` 2025-11-01 (newest GA), role
assignments 2022-04-01, `Microsoft.Network` 2025-01-01 (newest in the local
Bicep type index), locks 2020-05-01 and
`Microsoft.Insights/diagnosticSettings` 2021-05-01-preview (the version AVM
and the Container Apps composition use).

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
revert inputs through the owning IaC tool and review the plan. Images deleted by
retention or by hand, a deleted registry, DNS records, removed grants and lock
removals are not undone by a source revert. Removing the retention property
from a source may leave the policy enabled; confirm with
`az acr config retention show` and disable it with the CLI command above. A
Bicep incremental deployment leaves a removed role assignment or diagnostic
setting in place, so delete it explicitly. Logs already ingested stay in the
workspace for its retention period. Never switch Bicep/Terraform ownership by
applying the other source; review import and state migration first.

## Sources

Checked on 2026-11-11:

- [Authentication options](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-authentication)
  and [Entra permissions and roles](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-rbac-built-in-roles-overview).
- [Zone redundancy is on by default](https://learn.microsoft.com/en-us/azure/container-registry/zone-redundancy)
  (the `zoneRedundancy` property is legacy).
- [Retention policy for untagged manifests](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-retention-policy)
  (preview, Premium, digest warning) and
  [image locks](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-image-lock).
- [Private Link](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-private-link)
  (Premium, data endpoints, unsupported Azure DevOps-hosted agents),
  [trusted services](https://learn.microsoft.com/en-us/azure/container-registry/allow-access-trusted-services)
  and [import images](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-import-images)
  (network-restricted targets, importer role).
- [Azure private networking for GitHub-hosted runners](https://docs.github.com/en/organizations/managing-organization-settings/about-azure-private-networking-for-github-hosted-runners-in-your-organization)
  and [Managed DevOps Pools networking](https://learn.microsoft.com/en-us/azure/devops/managed-devops-pools/configure-networking).
- [Monitoring data reference](https://learn.microsoft.com/en-us/azure/container-registry/monitor-container-registry-reference)
  (`ContainerRegistryLoginEvents`, `ContainerRegistryRepositoryEvents`).
- [Registry schema 2025-11-01](https://learn.microsoft.com/en-us/azure/templates/microsoft.containerregistry/2025-11-01/registries),
  [role assignment schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2022-04-01/roleassignments),
  [private endpoint schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2025-01-01/privateendpoints)
  and [lock schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2020-05-01/locks).
