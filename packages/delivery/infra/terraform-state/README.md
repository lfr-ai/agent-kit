# Terraform remote state storage (opt-in)

One storage account and a `tfstate` blob container for the azurerm backend,
with Entra ID access only: Shared Key (account keys and SAS) is disabled, and
the CI identity receives `Storage Blob Data Contributor` on the container.
Blob versioning and soft delete keep earlier state recoverable. Choose **one**
canonical implementation: [Bicep](bicep/main.bicep) **or**
[Terraform](terraform/main.tf), never both over the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. The caller owns the resource group, the CI
identity and provider authentication.

## What is included

| Part | Reason |
| --- | --- |
| Storage account (StorageV2) | Shared Key and anonymous blob access disabled, minimum TLS 1.2; everything else is a secure default. |
| Blob service settings | Versioning on every write; blob and container soft delete for 30 days. |
| `tfstate` container | Private container for state blobs. |
| `Storage Blob Data Contributor` role assignment | CI reads, writes and leases (locks) state on this container only. |
| Storage firewall | Deny by default; only `allowedIpRanges` reach the account over the public endpoint. |
| Optional blob private endpoint | When `privateEndpoint` is set: endpoint, DNS zone group, and public network access `Disabled`. |
| Production `CanNotDelete` lock | Toolkit production policy, scoped to the account only. |
| Input guards | Reject locally redundant staging or production state, a malformed `privateEndpoint`, and invalid or conflicting `allowedIpRanges`. |

There is no diagnostic setting: the workspace is usually managed by the
Terraform that needs this account first. See
[REFERENCE.md](REFERENCE.md#network-and-logging-trade-off).

> **Breaking change:** the account now denies public clients by default. An
> empty `allowedIpRanges` without `privateEndpoint` blocks **every** runner,
> including GitHub-hosted and Microsoft-hosted Azure DevOps agents, whose
> addresses are not stable. Use self-hosted runners with a fixed egress
> address in `allowedIpRanges`, or VNet-attached runners with
> `privateEndpoint`.

## Inputs

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Required | Meaning |
| --- | --- |
| `location` | Azure public-cloud region |
| `name` | 3–24 lowercase letters and digits, globally unique; one account per stage |
| `stage` | `dev`, `test`, `staging`, `prod` |
| `principalId` | Object (principal) ID of the existing CI identity, **not** its client ID |
| `resource_group_id` | Terraform only: existing resource group ARM ID |

| Optional | Default | Meaning |
| --- | --- | --- |
| `sku` | `Standard_ZRS` | Also `Standard_LRS` or `Standard_GZRS` |
| `privateEndpoint` | none | `{ subnetId, privateDnsZoneId }`: an existing subnet ARM ID and an existing `privatelink.blob.core.windows.net` zone ARM ID |
| `allowedIpRanges` | `[]` | Public IPv4 addresses or CIDR ranges allowed through the firewall; only without `privateEndpoint`. Storage rejects `/31` and `/32`: pass a bare address instead |

| Stage | Replication | Network | Lock |
| --- | --- | --- | --- |
| `dev`, `test` | Any of the three; zone-redundant by default | Firewall deny + `allowedIpRanges`, or private endpoint | None |
| `staging` | **`Standard_ZRS` or `Standard_GZRS`** | Same as dev/test | None |
| `prod` | **`Standard_ZRS` or `Standard_GZRS`** | Same as dev/test | `CanNotDelete` |

The private endpoint stays optional in every stage, because the first
Terraform run often has no VNet or VNet-attached runner yet. Staging gets the
production replication guard so that state survives a zone outage before
release; the lock stays production-only so staging can be torn down.

Outputs: storage account resource ID, storage account name and container name.

## Bootstrap order

This account must exist before any Terraform root can use it as a backend.

1. **Deploy this composition first, without remote state.** Either deploy
   `bicep/main.bicep` (no state file at all; simplest), or apply `terraform`
   from a small bootstrap root that has no `backend` block, so Terraform keeps
   local state.
2. If you used Terraform, add the backend block below to the bootstrap root and
   run `terraform init -migrate-state`. Confirm the state blob exists, then
   delete the local `terraform.tfstate` and its backup.
3. Every other root module uses the same backend block with its own `key`.

The person who migrates state needs `Storage Blob Data Contributor` on the
container too; grant it temporarily or migrate as the CI identity.

For the Bicep path, this is a **separate approved operator operation**, not run by
the identity bootstrap. Replace placeholders and review storage/role-write
permissions before executing:

```powershell
az deployment group create `
  --subscription SUBSCRIPTION_UUID `
  --resource-group PROJECT_RESOURCE_GROUP `
  --name bootstrap-terraform-state `
  --template-file packages/delivery/infra/terraform-state/bicep/main.bicep `
  --parameters location=REGION name=UNIQUE_STORAGE_NAME stage=dev `
    principalId=IDENTITY_PRINCIPAL_UUID sku=Standard_ZRS `
    'allowedIpRanges=[\"RUNNER_EGRESS_IP\"]' `
  --only-show-errors
```

The `\"` escaping preserves JSON quotes through `az.cmd` on Windows. Public
access remains firewall-denied except for approved fixed egress addresses; hosted
runners do not have a fixed address by default. Alternatively, supply the private
endpoint and use network/DNS-reachable self-hosted runners. Never grant Owner just
to make bootstrap work. Keep blob versioning/soft-delete recovery and applicable
resource locks. Local bootstrap state is temporary operator material, never a CI
backend, committed file or preview artifact.

## Backend block for consumers

```hcl
terraform {
  backend "azurerm" {
    use_azuread_auth     = true
    storage_account_name = "<storage account name output>"
    container_name       = "tfstate"
    key                  = "<workload>/<stage>.tfstate"
  }
}
```

Keep authentication out of the file. In CI set `ARM_USE_OIDC=true`,
`ARM_CLIENT_ID` and `ARM_TENANT_ID` for workload identity federation; locally,
an `az login` session is used. `use_azuread_auth` is required because the
account rejects Shared Key, so the backend cannot fetch an access key. State
locking uses blob leases and needs no extra resource.

## Verify and adopt

From the repository root using installed tools:

```powershell
uv run --locked pytest tests\integration\delivery\infra\test_terraform_state.py -m integration -q
```

The tests use the repository's installed pinned Bicep/Terraform toolchain and the
**Azure/azapi 2.13.0** pin. Full Terraform validation reuses the
`CONTAINER_APPS_AZAPI_MIRROR` provider mirror. Missing tools or providers are
skips, not live validation.

Before adoption, rollback is removal of these sources and their test. After
adoption, state written to the account and locks are not undone by a source
revert. See [operator gates, rollback and sources](REFERENCE.md).
