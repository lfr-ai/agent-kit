# Azure Database for PostgreSQL flexible server (opt-in)

One PostgreSQL 18 flexible server with one application database and a supplied
Microsoft Entra administrator. Authentication is **Entra ID only**: password
authentication is disabled, so no administrator login, password or connection
secret exists in parameters, state or outputs.
Choose **one** canonical implementation: [Bicep](bicep/main.bicep) **or**
[Terraform](terraform/main.tf), never both over the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Reference `bicep/main.bicep` as a
resource-group-scoped module or `terraform` as a local Terraform child module.
The caller owns the resource group, Entra principals, network, provider
authentication and state.

## What is included

| Part | Reason |
| --- | --- |
| Flexible server | PostgreSQL 18, Entra-only authentication, `storageSizeGB` (default 32 GiB) storage with autogrow. Only non-default settings are declared. |
| Entra administrator | The supplied user, group or service principal; it creates the app's database role. |
| Application database | One database named by `databaseName`, with the server's default charset and collation. |
| Extension allowlist | Only when `extensions` is supplied, for example `vector` (pgvector) or `age` (Apache AGE graph). |
| Private endpoint and DNS zone group | Only when `privateEndpoint` is supplied. Public access is disabled unless dev or test opts in. |
| Firewall rules | Only with the dev/test `allowPublicNetworkAccess` opt-in: one rule per `allowedIpRanges` entry. |
| Diagnostic settings | Only when `logAnalyticsWorkspaceId` is supplied: `PostgreSQLLogs` and `AllMetrics` to that workspace. |
| Production `CanNotDelete` lock | Toolkit production policy, scoped to the server only. |
| Input guards | Reject unsafe combinations before deployment; they do not prove permissions, quota or regional capacity. |

Private networking uses a **private endpoint**, not VNet integration. Microsoft
recommends Private Link as the alternative to VNet integration. It needs no
dedicated delegated subnet. It also keeps one networking mode across stages:
dev can opt in to a firewalled public endpoint while prod is private. A
VNet-integrated server can't use
Private Link and can't change its network mode after creation.

## Inputs

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Required | Meaning |
| --- | --- |
| `location` | Azure public-cloud region; production needs availability zones and an Azure region pair |
| `name` | Globally unique, 3–63 lowercase letters, digits or hyphens |
| `stage` | `dev`, `test`, `staging`, `prod`; separate names/groups/state per stage |
| `administrator` | Existing Entra principal: `objectId`, `name` (display name) and `type` (`User`, `Group`, `ServicePrincipal`). Prefer a group. |
| `databaseName` | Application database name |
| `resource_group_id` | Terraform only: existing resource group ARM ID |

Optional: `sku` (stage default), `storageSizeGB` (`32`, the smallest
Premium SSD size; raise it only, because storage never shrinks),
`privateEndpoint` (none), `allowPublicNetworkAccess` (`false`),
`allowedIpRanges` (`[]`),
`logAnalyticsWorkspaceId` (none, no diagnostics; an empty string is rejected)
and `extensions` (none allowed). `sku` holds `name` and `tier`
(`Burstable`, `GeneralPurpose`, `MemoryOptimized`). `privateEndpoint` holds
`subnetId` and `privateDnsZoneId`, as exact-case ARM IDs. Both must exist
already, and the `privatelink.postgres.database.azure.com` zone must be linked
to the VNet. `allowedIpRanges` takes IPv4 addresses or CIDR ranges; each
becomes a firewall rule from its first to its last address.
`extensions` lists lowercase extension names for the `azure.extensions` server
parameter. Allowing an extension does not install it: the administrator still
runs `create extension` in each database that needs it. `age` also needs a
preload and restart; see [extensions](REFERENCE.md#extensions).

| Stage | Network | Compute | Resilience | Diagnostics | Lock |
| --- | --- | --- | --- | --- | --- |
| `dev`, `test` | Public access disabled by default; private endpoint, or `allowPublicNetworkAccess` with `allowedIpRanges` firewall rules, optional | `Standard_B1ms` (Burstable) | Platform defaults: no HA, locally redundant 7-day backups | Optional workspace | None |
| `staging` | **Private endpoint required**; public access disabled | `Standard_B1ms` (Burstable) unless `sku` is set | Platform defaults | **Workspace required** | None |
| `prod` | **Private endpoint required**; public access disabled | `Standard_D2ds_v5` (General Purpose); **Burstable rejected** | **Zone-redundant HA** and **geo-redundant backup** | **Workspace required** | `CanNotDelete` |

Staging gets the production security guards (private endpoint, diagnostics) but
not the production cost and availability choices: zone-redundant HA,
geo-redundant backup and a larger default size roughly double or triple the
bill and add nothing to a security review. Set `sku` to rehearse production
sizing. Breaking change: dev and test callers that relied on the public
endpoint must now set `allowPublicNetworkAccess` and their client ranges.

The opt-in public endpoint admits only `allowedIpRanges`; with an empty list
nobody can connect. Don't add the `0.0.0.0` "allow Azure
services" rule: it admits connections from every Azure subscription, including
other customers'.

Outputs: server ID, `fqdn` and database name.

## Connect the app with a managed identity

1. The Entra administrator connects to the `postgres` database with an access
   token, then creates a role for the app identity. The role name must be the
   identity's Entra display name; for a managed identity, use its resource name.

   ```sql
   select * from pgaadauth_create_principal('app-identity-name', false, false);
   ```

2. The administrator connects to the application database and grants only what
   the app needs, for example:

   ```sql
   grant connect on database app to "app-identity-name";
   grant usage on schema public to "app-identity-name";
   grant select, insert, update, delete on all tables in schema public to "app-identity-name";
   ```

3. The app requests a token for scope
   `https://ossrdbms-aad.database.windows.net/.default` with its managed identity
   (for example `DefaultAzureCredential`, or `ManagedIdentityCredential` with a
   user-assigned identity's *client* ID). It connects to `fqdn` with
   `sslmode=require` and uses the role name as the user and the token as the
   password. Tokens expire, so request one for each new connection, for example
   in the pool's connect hook; the credential caches and refreshes it. This
   package adds no client dependency.

## Verify and adopt

From the repository root using installed tools:

```powershell
uv run --locked pytest tests\integration\delivery\infra\test_postgresql.py -q
```

The tests use the same Bicep 0.39.26 / Terraform 1.11.3 baseline and
**Azure/azapi 2.13.0** pin as Container Apps. Full Terraform validation reuses
the `CONTAINER_APPS_AZAPI_MIRROR` provider mirror. Missing tools or providers
are skips, not live validation.

Before adoption, rollback is removal of these sources and their test. After
adoption, database contents, the backup redundancy choice, DNS records, locks
and logs already sent to the workspace are not undone by a source revert.
See [operator gates, rollback and sources](REFERENCE.md).
