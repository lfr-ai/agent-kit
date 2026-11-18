# Cosmos DB: operator gates, validation and sources

Start with the [consumer contract](README.md).

## Defaults this composition relies on

The sources declare only what differs from the platform default or what the
API needs. They deliberately **do not restate** these 2025-10-15 defaults: the
`GlobalDocumentDB` kind (the NoSQL API, not Gremlin, MongoDB, Cassandra or
Table), session consistency, a single write region without automatic or
multi-region writes, the `Hash` partition key kind, no analytical store, no
free tier. In dev, test and staging, periodic backup and no zone redundancy
also stay at their defaults.

Declared on purpose:

- `databaseAccountOfferType: Standard` and one `locations` entry: required by
  the API. The write region is `location` with failover priority 0.
- `disableLocalAuth: true`: account keys and resource tokens are rejected, so
  only Entra ID tokens authorize data-plane requests. No key is ever read,
  listed or output.
- `minimalTlsVersion: Tls12`: the template reference still documents TLS 1.0
  as the unset minimum; the TLS article says new accounts default to TLS 1.2
  and older versions are retired. Declaring it removes the ambiguity.
- Dev, test and staging: the `EnableServerless` capability.
- Production only: `isZoneRedundant: true` on the region,
  `backupPolicy.type: Continuous` with the `Continuous30Days` tier (the tier is
  declared because the reference documents no default), and database-level
  autoscale `maxThroughput` (default 1000 RU/s) when a database is supplied.
- Containers: `partitionKey.version: 2` (large partition keys) because the API
  default, version 1, hashes only a prefix of long key values.
- `publicNetworkAccess: Disabled` in every stage, unless a dev or test caller
  sets `allowPublicNetworkAccess`; that opt-in instead declares `ipRules` from
  `allowedIpRanges` (at least one, because an empty list means all networks).

Because defaults are not declared, a source deployment doesn't revert drift if
someone re-enables local authentication. Enforce it with the built-in Azure
Policy for Cosmos DB local authentication or a post-deployment check on
`disableLocalAuth`.

## Operator gates and ownership

- **Data-plane RBAC.** The optional assignment uses the built-in **Cosmos DB
  Built-in Data Contributor** role (`00000000-0000-0000-0000-000000000002`) at
  account scope. It is a `sqlRoleAssignments` child of the account, not an Azure
  RBAC role assignment. Narrower scopes (`/dbs/<db>` or
  `/dbs/<db>/colls/<container>`) and the read-only Data Reader
  (`00000000-0000-0000-0000-000000000001`) belong in the owner's own reviewed
  assignment. The deployer needs permission for
  `Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments/write`.
- **Capacity and resilience.** Serverless accounts run in one region and don't
  accept throughput settings, so dev/test databases declare none. Production
  shares autoscale throughput across the database's containers; a container
  needing dedicated throughput needs a reviewed change. Zone redundancy needs a
  region with availability zones and capacity; check before choosing
  `location`. Neither capacity nor zone support is verifiable offline.
- **Create-time choices.** Capacity mode, zone redundancy and partition keys
  are chosen at creation; changing them later is limited or impossible and
  usually means a new account or container plus a data migration. Continuous
  backup can't be switched back to periodic.
- **Continuous backup.** Point-in-time restore creates a **new** account; it
  doesn't roll back the existing one. The 30-day tier is billed per GB; the
  7-day tier is cheaper. Rehearse a restore before relying on it.
- For a private endpoint, provide an existing same-region subnet and an existing
  `privatelink.documents.azure.com` zone with a VNet link. The `Sql` group ID
  serves the NoSQL API. Clients keep using `documentEndpoint`, which resolves to
  the private address. Private clients, including CI jobs, need VNet reachability
  and private DNS.
- In dev/test without a private endpoint the account is private by default:
  set `allowPublicNetworkAccess` with an IP allow list to reach it from a
  workstation or hosted runner. Even then it accepts only Entra tokens.
  Existing dev/test accounts that relied on the old public default lose public
  access on the next deployment.
- The production lock covers the account and is inherited by its children:
  changing or removing databases, containers or role assignments in production
  needs a reviewed lock removal. The lock does **not** stop data-plane deletes
  of items by an authorized identity, nor an actor who may remove locks. The
  Terraform lock depends on the managed children, so creation puts it last and
  destroy removes it first; approvals must still deny unreviewed destruction.
- Diagnostics need an existing Log Analytics workspace (required in
  production). Resource-specific (`Dedicated`) tables are Microsoft's
  recommendation. `DataPlaneRequests` and `ControlPlaneRequests` are logged;
  query runtime and partition key statistics are extra cost; add them in the
  workspace owner's own setting if needed. Delete the diagnostic setting before
  deleting or re-creating the account with the same name.
- Register `Microsoft.DocumentDB` and confirm regional availability and quota.
- The guards accept only the Azure public-cloud private DNS zone, by exact ARM
  ID shape and casing, and a `Microsoft.Network/virtualNetworks/*/subnets/*`
  subnet ID.

## Offline checks and pins

Checked tool baseline: **Bicep 0.39.26** and **Terraform 1.11.3**. Terraform
pins **Azure/azapi 2.13.0** with hand-written request bodies. API versions:

| Resources | API version |
| --- | --- |
| Account, SQL database, container, SQL role assignment | `Microsoft.DocumentDB` `2025-10-15` |
| Private endpoint and DNS zone group | `Microsoft.Network` `2025-01-01` |
| Diagnostic setting | `2021-05-01-preview` |
| Resource lock | `2020-05-01` |

`2025-10-15` is the newest GA `Microsoft.DocumentDB` version in both the local
Bicep type index and the azapi 2.13.0 embedded schema. Newer GA versions exist
but aren't in that index; adopt one as a separate reviewed change with a
matching Bicep upgrade. No external modules, restore or provider download.

The integration test relocates the exact source closure, then runs Bicep
format, lint, `build`, and `build-params` for the dev and prod examples. It
evaluates every exported guard with Bicep's native parameter evaluator,
including the production rejections, and checks that Bicep `guid()` and
Terraform `uuidv5()` produce the same role-assignment name. Terraform runs
`fmt -check` and runs `validate -json` / `test -no-color` against the
**unchanged variables.tf alone** with the same positive and negative cases.

Full resource validation and the mocked plans in `terraform/tests` need the
reviewed Azure/azapi 2.13.0 mirror. Set `CONTAINER_APPS_AZAPI_MIRROR`; tests
then run `terraform init -backend=false -input=false -get=false
-plugin-dir=<mirror>`. **No mirror means a reported skip, not a
provider-validation pass.** Mocks do not certify ARM behavior, regional
capacity, policies or permissions.

## Rollback

Before deployment, remove this directory, its integration test, its catalog
entry and the delivery README row; no cloud state has changed. After adoption,
revert inputs through the owning IaC tool and review the plan. Deleted items,
containers, databases or accounts, the capacity mode, continuous backup,
partition keys, private DNS records, lock removals and ingested logs cannot be
undone by a source revert. Recover deleted data only through a point-in-time
restore into a new account. Removing `principalId` deletes the data-plane role
assignment in Terraform; a Bicep incremental deployment leaves it (and any
removed diagnostics, endpoint or lock) in place, so delete it explicitly.
Never switch Bicep/Terraform ownership by applying the other source; review
import and state migration first.

## Sources

Checked while authoring (Microsoft Learn):

- [Database account template reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.documentdb/2025-10-15/databaseaccounts),
  [SQL databases](https://learn.microsoft.com/en-us/azure/templates/microsoft.documentdb/2025-10-15/databaseaccounts/sqldatabases),
  [containers](https://learn.microsoft.com/en-us/azure/templates/microsoft.documentdb/2025-10-15/databaseaccounts/sqldatabases/containers)
  and [SQL role assignments](https://learn.microsoft.com/en-us/azure/templates/microsoft.documentdb/2025-10-15/databaseaccounts/sqlroleassignments).
- [Connect with role-based access control and Entra ID](https://learn.microsoft.com/en-us/azure/cosmos-db/how-to-connect-role-based-access-control)
  and [data-plane security reference](https://learn.microsoft.com/en-us/azure/cosmos-db/reference-data-plane-security)
  (built-in Data Reader/Contributor IDs, disabling local authentication).
- [Serverless account type](https://learn.microsoft.com/en-us/azure/cosmos-db/serverless)
  (single region, no provisioned throughput).
- [Continuous backup with point-in-time restore](https://learn.microsoft.com/en-us/azure/cosmos-db/continuous-backup-restore-introduction)
  (7/30-day tiers, restore into a new account).
- [Minimum TLS version enforcement](https://learn.microsoft.com/en-us/azure/cosmos-db/self-serve-minimum-tls-enforcement).
- [Configure private endpoints](https://learn.microsoft.com/en-us/azure/cosmos-db/how-to-configure-private-endpoints)
  (`Sql` group ID, `privatelink.documents.azure.com`).
- [Monitor with diagnostic settings](https://learn.microsoft.com/en-us/azure/cosmos-db/monitor-resource-logs)
  (resource-specific mode recommended) and
  [supported resource logs](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-logs/microsoft-documentdb-databaseaccounts-logs).
- [Private endpoint schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2025-01-01/privateendpoints),
  [lock schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2020-05-01/locks),
  [diagnostic-settings schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.insights/2021-05-01-preview/diagnosticsettings)
  and [resource locks](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/lock-resources).
- [Terraform azapi_resource 2.13.0](https://registry.terraform.io/providers/Azure/azapi/2.13.0/docs/resources/resource).
