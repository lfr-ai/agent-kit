# Managed Redis: operator gates, validation and sources

Start with the [consumer contract](README.md).

## Defaults this composition relies on

The sources declare only what differs from the platform default. They
deliberately **do not restate** these 2025-07-01 defaults: Entra ID
authentication, minimum TLS 1.2, encrypted client protocol, port 10000, high
availability, eviction policy, no persistence and zone placement. The one
security exception is `accessKeysAuthentication: Disabled`, declared on the
database so the Entra-only claim is part of the source and its tests. `publicNetworkAccess` is declared because this API version
requires it: `Disabled` unless `allowPublicNetworkAccess` is set. The same goes
for `enabled: true` on each diagnostic-setting log or metric
entry.

Because the other defaults are not declared, a source deployment does not
revert drift in them. A redeployment does turn access keys off again, but only
when it runs: enforce the security defaults between deployments with Azure
Policy or a post-deployment check on `accessKeysAuthentication`.

## Operator gates and ownership

- The app identity already exists. Pass its **object (principal) ID**. The
  application authenticates with the identity's client ID. The grant uses the
  built-in `default` access policy and is named after the object ID.
- For a private endpoint, provide an existing same-region subnet and an existing
  `privatelink.redis.azure.net` zone with a VNet link. Validate routing, DNS
  resolution from the app and subnet policies. Clients keep using the public
  host name, which resolves to the private address.
- Register `Microsoft.Cache` and confirm the region offers the chosen SKU.
  Changing the SKU tier or clustering policy can require a new cache.
- The production lock covers the cache and is inherited by its database and
  access assignment. Rotating `principalId` in production therefore needs a
  reviewed lock removal. A Bicep incremental deployment also leaves the
  previous assignment in place: remove stale grants explicitly.
- The lock does **not** block updates or an actor who may remove locks.
  Terraform destroy removes its own lock first; operator approvals must deny
  unreviewed destroy, replacement and lock removal.
- Diagnostics need an existing Log Analytics workspace (required in
  production). Azure Monitor exports platform metrics from the cluster resource
  and the only resource-log category, `ConnectionEvents` (table
  `REDConnectionEvents`), from the `default` database, so the composition writes
  one setting on each. This is the same split the AVM `redis-enterprise` module
  uses. The deploying identity needs diagnostic-settings write access on the
  cache and access to the workspace, which may sit in another subscription. Log
  ingestion and retention are billed by the workspace. Connection logs are
  event-based and may miss events, so retain them at least as long as client
  connections live. Active geo-replication needs a setting per cache.
- Delete the diagnostic settings before deleting, renaming or moving the cache:
  Azure Monitor can reapply leftover settings to a re-created resource with the
  same ID.
- The private endpoint and the database are created in parallel after the
  cache. Confirm in a first non-production deployment that this ordering works.
- The guards accept only Azure public-cloud private DNS zones.

## Offline checks and pins

Checked tool baseline: **Bicep 0.39.26** and **Terraform 1.11.3**. Terraform
pins **Azure/azapi 2.13.0**. API versions: `Microsoft.Cache` 2025-07-01,
`Microsoft.Network` 2025-01-01 (newest in the local Bicep type index), locks
2020-05-01 and `Microsoft.Insights/diagnosticSettings` 2021-05-01-preview (the
version AVM and the Container Apps composition use). No external modules,
restore or provider download.

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
provider-validation pass.** Mocks do not certify ARM behavior, policies or
permissions.

## Rollback

Before deployment, remove this directory, its integration test, its catalog
entry and the delivery README row; no cloud state has changed. After adoption,
revert inputs through the owning IaC tool and review the plan. Cache data,
replaced caches, private DNS records, removed grants and lock removals cannot
be undone by a source revert. Omitting the workspace input in dev/test makes
Terraform delete the diagnostic settings; a Bicep incremental deployment leaves
them in place, so delete them explicitly. Logs and metrics already ingested
stay in the workspace for its retention period. Never switch Bicep/Terraform
ownership by applying the other source; review import and state migration
first.

## Sources

From the task research, not re-fetched while authoring:

- [Azure Managed Redis overview](https://learn.microsoft.com/en-us/azure/redis/overview),
  [Entra ID authentication](https://learn.microsoft.com/en-us/azure/redis/entra-for-authentication),
  [private link](https://learn.microsoft.com/en-us/azure/redis/private-link)
  and [clustering policy](https://learn.microsoft.com/en-us/azure/redis/architecture).
- [Cluster schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.cache/2025-07-01/redisenterprise),
  [database schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.cache/2025-07-01/redisenterprise/databases)
  and [access assignment schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.cache/2025-07-01/redisenterprise/databases/accesspolicyassignments).
- [Private endpoint schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2025-01-01/privateendpoints)
  and [lock schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2020-05-01/locks).
- [redis-entraid client](https://github.com/redis/redis-py-entraid).

Diagnostics, checked on 2026-11-06:

- [Azure Managed Redis diagnostic settings](https://learn.microsoft.com/en-us/azure/redis/monitor-diagnostic-settings)
  (database-scoped `ConnectionEvents`, Log Analytics destination, event-based
  connection logs).
- [Supported logs for redisEnterprise/databases](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-logs/microsoft-cache-redisenterprise-databases-logs)
  and [supported metrics for redisEnterprise](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-metrics/microsoft-cache-redisenterprise-metrics)
  (diagnostic-settings export supported).
- [AVM avm/res/cache/redis-enterprise](https://github.com/Azure/bicep-registry-modules/tree/main/avm/res/cache/redis-enterprise):
  cluster metrics-only setting and database logs-only setting.
- [Diagnostic settings in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/data-collection/diagnostic-settings),
  [diagnostic-settings schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.insights/2021-05-01-preview/diagnosticsettings)
  and the [2021-05-01-preview REST spec](https://github.com/Azure/azure-rest-api-specs/blob/main/specification/monitor/resource-manager/Microsoft.Insights/Insights/preview/2021-05-01-preview/diagnosticsSettings_API.json)
  (`enabled` is required on each log and metric entry).
