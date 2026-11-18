# PostgreSQL: operator gates, validation and sources

Start with the [consumer contract](README.md).

## Defaults this composition relies on

The sources declare only what differs from the platform default or what the
API needs. They deliberately **do not restate** these 2025-08-01 defaults:
`Default` create mode, Premium SSD storage, 7-day backup retention, no
preferred availability zone, a system-managed maintenance window, encrypted
(TLS) connections, the `UTF8` / `en_US.utf8` database charset and
collation. In
dev/test, high availability and geo-redundant backup also stay at their
disabled defaults.

Declared on purpose:

- `version: '18'`: the newest GA major version. Check extension support before
  adoption: some extensions aren't available on PostgreSQL 18 yet.
- `authConfig`: Entra ID authentication is turned on and password
  authentication, which is on by default, is turned off. No administrator login
  or password is ever sent.
- `storage`: the API documents no default size, so `storageSizeGB` declares
  it, defaulting to the smallest Premium SSD size (32 GiB). Storage can grow but
  never shrink, so only raise it. Autogrow (off by default) is declared so a full
  disk grows online instead of making the server read-only.
- Production only: `highAvailability.mode: ZoneRedundant` and
  `backup.geoRedundantBackup: Enabled`.
- `network.publicNetworkAccess`: always declared, `Disabled` unless a dev or
  test caller without a private endpoint sets `allowPublicNetworkAccess`; that
  opt-in also creates one firewall rule per `allowedIpRanges` entry.

Because the defaults are not declared, a source deployment does not revert
drift if someone enables password authentication later. Enforce it with Azure
Policy or a post-deployment check on `authConfig.passwordAuth`.

## Operator gates and ownership

- The administrator principal already exists. Pass its **object ID** and its
  exact Entra **display name**, which becomes its PostgreSQL role name. Prefer an
  Entra group so access survives staff changes. The module never creates app
  roles inside PostgreSQL: the administrator runs `pgaadauth_create_principal`
  on the `postgres` database, as the README shows. This keeps database
  privileges out of the ARM control plane.
- **Region constraints (production).** Zone-redundant HA needs a region with
  availability zones and isn't offered on Burstable or in single-zone regions.
  The `sku` guard enforces the Burstable rule. Geo-redundant backup is only
  available in regions with an Azure region pair; it restores into the paired
  region. Check the region list for both before choosing `location`; neither
  is verifiable offline.
- **Create-time choices.** Geo-redundant backup can only be chosen at server
  creation, so changing it means a new server and a data migration.
  VNet-integrated servers can't use private endpoints, and a backup can't be
  restored across the two network modes, so switching modes also means a new
  server.
- Major-version upgrades are in-place but one-way. Changing `version` in source
  only makes sense after a reviewed upgrade plan.
- For a private endpoint, provide an existing same-region subnet and an existing
  `privatelink.postgres.database.azure.com` zone with a VNet link. Validate
  routing, DNS resolution from the app and subnet policies. Clients keep using
  the public `fqdn`, which resolves to the private address.
- In dev/test without a private endpoint, public access stays disabled unless
  the caller sets `allowPublicNetworkAccess`; then only `allowedIpRanges` get
  firewall rules, and an empty list refuses every connection. Rules are
  created one at a time after the database. Don't add the `0.0.0.0` "allow
  Azure services" rule.
- The administrator, database and private endpoint are created one after
  another, because parallel operations on one server can be rejected. Confirm
  in a first non-production deployment that this ordering works.
- The production lock covers the server and is inherited by its children.
  Changing the administrator or database in production therefore needs a
  reviewed lock removal. The lock does **not** block updates or an actor who
  may remove locks. Terraform destroy removes its own lock first; operator
  approvals must deny unreviewed destroy, replacement and lock removal.
- Diagnostics need an existing Log Analytics workspace (required in
  staging and production). `PostgreSQLLogs` carries the server log: errors, plus
  connections and statements as the logging server parameters allow. Query
  Store, session and table statistics categories
  are extra cost; add them in the workspace owner's own setting if needed. Log
  ingestion and retention are billed by the workspace. Delete the diagnostic
  setting before deleting or re-creating the server with the same name.
- Register `Microsoft.DBforPostgreSQL` and confirm the region offers the
  chosen compute size and quota.
- The guards accept only Azure public-cloud private DNS zones, by exact ARM ID
  shape and casing, and a `Microsoft.Network/virtualNetworks/*/subnets/*`
  subnet ID.

## Extensions

Azure allows no extension until it is named in the `azure.extensions` server
parameter. The `extensions` input sets that parameter as one comma-separated
value. It is a dynamic parameter, so the change needs no restart. It is applied
after the database and before the private endpoint, because operations on one
server run one at a time.

- Allowing is not installing. The administrator runs `create extension vector;`
  (or `age`) in each database that needs it, with the same access-token login
  as for role creation.
- `age` must also be in `shared_preload_libraries`, a static parameter that
  needs a server restart. The module does not manage it: its default differs
  by PostgreSQL version, and a declared value replaces that default instead of
  adding to it. Add `age` to the current value with the portal or
  `az postgres flexible-server parameter set`, then restart in a maintenance
  window. `vector` needs no preload.
- Check that each extension and version is offered for PostgreSQL 18 before
  adding it.
- An empty list declares nothing, and server parameters can't be deleted. Removing
  the input or emptying the list therefore leaves the last allowlist in place in
  both Bicep and Terraform. To revoke an extension, set a shorter list, or reset
  the parameter to its default outside this module.

## Offline checks and pins

Checked tool baseline: **Bicep 0.39.26** and **Terraform 1.11.3**. Terraform
pins **Azure/azapi 2.13.0**. API versions: `Microsoft.DBforPostgreSQL`
2025-08-01, `Microsoft.Network` 2025-01-01, locks 2020-05-01 and
`Microsoft.Insights/diagnosticSettings` 2021-05-01-preview (the version AVM and
the sibling compositions use). These are the newest GA versions in the local
Bicep type index. A newer GA PostgreSQL API exists but is not yet in that index.
Adopt it as a separate reviewed change with a matching Bicep upgrade. No
external modules, restore or provider download.

The integration test relocates the exact source closure, then runs Bicep
format, lint, `build`, and `build-params` for the dev and prod examples. It
evaluates every exported guard with Bicep's native parameter evaluator,
including the production rejections. Terraform runs `fmt -check` and runs
`validate -json` / `test -no-color` against the **unchanged variables.tf
alone** with the same positive and negative cases as Bicep.

Full resource validation and the mocked plans in `terraform/tests` need the
reviewed Azure/azapi 2.13.0 mirror that Container Apps uses. Set
`CONTAINER_APPS_AZAPI_MIRROR`; tests then run `terraform init -backend=false
-input=false -plugin-dir=<mirror>`. **No mirror means a reported skip, not a
provider-validation pass.** Mocks do not certify ARM behavior, regional
capacity, policies or permissions.

## Rollback

Before deployment, remove this directory, its integration test, its catalog
entry and the delivery README row; no cloud state has changed. After adoption,
revert inputs through the owning IaC tool and review the plan. Database
contents, a deleted server, the geo-redundant backup choice, database roles
created with SQL, private DNS records and lock removals cannot be undone by a
source revert. Recover a deleted server only through the service's
deleted-server restore; the production lock exists to prevent that case.
Omitting the workspace input in dev/test makes Terraform delete the
diagnostic setting; a Bicep incremental deployment leaves it in place, so
delete it explicitly. Logs already ingested stay in the workspace for its
retention period. Never switch Bicep/Terraform ownership by applying the other
source; review import and state migration first.

## Sources

Checked while authoring:

- [Supported PostgreSQL versions](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/concepts-supported-versions)
  (PostgreSQL 18 GA).
- [Microsoft Entra authentication](https://learn.microsoft.com/en-us/azure/postgresql/security/security-entra-concepts),
  [manage Entra roles](https://learn.microsoft.com/en-us/azure/postgresql/security/security-manage-entra-users)
  and [connect with a managed identity](https://learn.microsoft.com/en-us/azure/postgresql/security/security-connect-with-managed-identity)
  (`pgaadauth_create_principal` on the `postgres` database; token scope
  `https://ossrdbms-aad.database.windows.net/.default`).
- [High availability](https://learn.microsoft.com/en-us/azure/postgresql/high-availability/concepts-high-availability)
  (zone-redundant HA not on Burstable or single-zone regions) and
  [reliability guide](https://learn.microsoft.com/en-us/azure/reliability/reliability-database-postgresql).
- [Backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore)
  (geo-redundant backup only at creation, paired regions, 7-day default
  retention).
- [Compute options](https://learn.microsoft.com/en-us/azure/postgresql/compute-storage/concepts-compute)
  and [storage](https://learn.microsoft.com/en-us/azure/postgresql/compute-storage/concepts-storage).
- [Private Link networking](https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private-link),
  [VNet integration](https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private)
  and [public access](https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-public).
- [Supported resource logs](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-logs/microsoft-dbforpostgresql-flexibleservers-logs).
- [Security baseline](https://learn.microsoft.com/en-us/security/benchmark/azure/baselines/azure-database-for-postgresql-flexible-server-security-baseline)
  and [Well-Architected service guide](https://learn.microsoft.com/en-us/azure/well-architected/service-guides/postgresql).
- [Flexible server schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.dbforpostgresql/2025-08-01/flexibleservers),
  [administrator schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.dbforpostgresql/2025-08-01/flexibleservers/administrators)
  and [database schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.dbforpostgresql/2025-08-01/flexibleservers/databases).
- [Private endpoint schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2025-01-01/privateendpoints),
  [lock schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2020-05-01/locks)
  and [diagnostic-settings schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.insights/2021-05-01-preview/diagnosticsettings).
- [Terraform azapi_resource 2.13.0](https://registry.terraform.io/providers/Azure/azapi/2.13.0/docs/resources/resource)
  and [azapi_update_resource](https://registry.terraform.io/providers/Azure/azapi/2.13.0/docs/resources/update_resource).
- [Allow extensions](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-allow-extensions),
  [extensions by engine version](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-by-engine),
  [Apache AGE](https://learn.microsoft.com/en-us/azure/postgresql/azure-ai/generative-ai-age-overview)
  and [shared library preloading](https://learn.microsoft.com/en-us/azure/postgresql/server-parameters/param-client-connection-defaults-shared-library-preloading).
- [Configuration schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.dbforpostgresql/2025-08-01/flexibleservers/configurations).
