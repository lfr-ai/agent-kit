# Azure Container Registry (opt-in)

One container registry with Entra ID access only: `AcrPull` for the app's
**existing** identity and, optionally, `AcrPush` for a CI identity. The admin
user and anonymous pull are disabled explicitly, and no credential is read or
output. Choose **one** canonical implementation:
[Bicep](bicep/main.bicep) **or** [Terraform](terraform/main.tf), never both over
the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Reference `bicep/main.bicep` as a
resource-group-scoped module or `terraform` as a local Terraform child module.
The caller owns the resource group, identities, network, workspace, provider
authentication and state.

## What is included

| Part | Reason |
| --- | --- |
| Registry | The service itself. Only non-default settings are declared. Zone redundancy is automatic in regions with availability zones. |
| `AcrPull` role assignment | The app pulls images through Entra ID; no admin user or token. |
| `AcrPush` role assignment | Only when `pushPrincipalId` is supplied, for the CI identity. |
| Private endpoint and DNS zone group | Only when `privateEndpoint` is supplied (Premium). |
| Public network access | Disabled unless dev or test sets `allowPublicNetworkAccess`; Premium then denies all but `allowedIpRanges`. |
| Diagnostic setting | Only when `logAnalyticsWorkspaceId` is supplied: login and repository events. |
| Production retention policy | Untagged manifests are deleted after the default 7 days (Premium preview feature). |
| Production `CanNotDelete` lock | Toolkit production policy, scoped to the registry only. |
| Input guards | Reject unsafe production inputs before deployment; they do not prove permissions or capacity. |

## Inputs

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Required | Meaning |
| --- | --- |
| `location` | Azure public-cloud region |
| `name` | 5–50 letters and digits, globally unique; separate names per stage |
| `stage` | `dev`, `test`, `staging`, `prod` |
| `pullPrincipalId` | Object (principal) ID of the existing app identity, **not** its client ID |
| `resource_group_id` | Terraform only: existing resource group ARM ID |

Optional: `pushPrincipalId` (none), `sku` (`Basic`), `privateEndpoint` (none)
with `subnetId` and `privateDnsZoneId`, `allowPublicNetworkAccess` (`false`),
`allowedIpRanges` (`[]`, Premium only) and `logAnalyticsWorkspaceId` (none,
no diagnostics; an empty string is rejected). The subnet, the `privatelink.azurecr.io` zone and its VNet
link, and the workspace must already exist.

| Stage | SKU | Network | Untagged retention | Diagnostics | Lock |
| --- | --- | --- | --- | --- | --- |
| `dev`, `test` | Basic or Standard need `allowPublicNetworkAccess` (public, Entra ID only); **Premium** for private access, IP rules or a private endpoint | Public access disabled unless opted in; private endpoint optional | Off | Optional workspace | None |
| `staging` | **Premium** (implied by the private endpoint) | **Private endpoint required**; public access disabled | Off | **Workspace required** | None |
| `prod` | **Premium required** | **Private endpoint required**; public access disabled | 7 days | **Workspace required** | `CanNotDelete` |

Staging gets the production security guards (private endpoint, audit logs)
but not retention or the lock, so pre-release images can be cleaned freely.
Breaking change: Basic or Standard callers in dev and test must now set
`allowPublicNetworkAccess = true` explicitly.

Outputs: registry resource ID and login server. Reference images by digest,
for example `<loginServer>/app@sha256:…`, as the Container Apps composition
requires.

## Hosted CI and the private production registry

Production has no public-access exception: Microsoft-hosted Azure DevOps
agents and standard GitHub-hosted runners cannot reach a registry whose public
access is disabled. The simplest secure path keeps hosted CI and needs no
network change:

1. Hosted CI builds once and pushes to the **test** registry, which the caller
   keeps public (`allowPublicNetworkAccess`) with Entra ID only. Its `pushPrincipalId` is the CI identity.
2. Promotion copies the tested digest into production with
   `az acr import --name <prod> --source <test>.azurecr.io/app@sha256:… --image app:<build-tag>`.
   Import runs inside Azure and passes the production network rules through
   the default trusted-services bypass. The promoting identity needs
   `Container Registry Data Importer and Data Reader` on production and
   `AcrPull` on test; grant both outside this composition.

If production must receive pushes directly, run CI inside the VNet instead:
self-hosted runners, GitHub-hosted larger runners with Azure private networking
(GitHub Team or Enterprise Cloud), or Azure DevOps Managed DevOps Pools injected
into the VNet. Then pass the CI identity as `pushPrincipalId` in production.
The trade-offs are in [REFERENCE.md](REFERENCE.md#hosted-ci-trade-off).

## Verify and adopt

From the repository root using installed tools:

```powershell
uv run --locked pytest tests\integration\delivery\infra\test_container_registry.py -m integration -q
```

The tests use the Bicep 0.39.26 / Terraform 1.11.3 baseline and the
**Azure/azapi 2.13.0** pin. Full Terraform validation reuses the
`CONTAINER_APPS_AZAPI_MIRROR` provider mirror. Missing tools or providers are
skips, not live validation.

Before adoption, rollback is removal of these sources and their test. After
adoption, images deleted by retention, DNS records, locks and logs already sent
to the workspace are not undone by a source revert.
See [operator gates, rollback and sources](REFERENCE.md).
