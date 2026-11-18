# AI Search: operator gates, validation and sources

Start with the [consumer contract](README.md).

## Defaults this composition relies on

The sources declare only what differs from the platform default. They
deliberately **do not restate** these 2025-05-01 defaults: one partition,
default hosting mode, one replica (dev/test), the free semantic ranker plan
(dev/test), Microsoft-managed encryption keys and no IP firewall rules unless
the public opt-in supplies them.

Declared on purpose:

- `disableLocalAuth: true`: API keys are allowed by default. With keys disabled,
  `authOptions` must stay absent, and the data plane accepts Entra tokens only.
- `sku`: required; `basic` in dev/test/staging, `standard` in production.
- Production only: `replicaCount` (2 unless set higher) for the availability
  SLA, and `semanticSearch: standard` so semantic queries keep working after
  the free monthly allowance.
- `publicNetworkAccess: Disabled` in every stage, unless dev or test sets
  `allowPublicNetworkAccess` without a private endpoint; then
  `networkRuleSet.ipRules` holds `allowedIpRanges`. Search treats an empty IP
  rule list as all networks, so the opt-in requires at least one range.

Because the defaults are not declared, a source deployment does not revert
drift if someone re-enables API keys later. Enforce it with Azure Policy or a
post-deployment check on `disableLocalAuth`.

## Operator gates and ownership

- The app identity already exists. Pass its **object (principal) ID**; the
  application authenticates with the identity's client ID. Both grants use
  `principalType: ServicePrincipal`, so supply managed identities or service
  principals, not users or groups.
- `Search Index Data Contributor` loads and deletes documents. Creating or
  changing indexes, indexers, data sources and skillsets needs
  `Search Service Contributor` (`7ca78c08-252a-4471-8644-bb5ff32d4ba0`). It is a
  broader management-plane role, so grant it separately to the pipeline or
  operator identity that publishes index definitions.
- **SLA and zones.** The availability SLA needs a billable tier with at least
  two replicas for read-only (query) workloads and three for read-write
  (query and indexing). The production guard enforces two; set three when the
  app also indexes in production. Replicas spread across availability zones
  only in regions that support them; check the region before choosing
  `location`. Basic allows at most three replicas.
- **Tier changes.** Existing services can switch between Basic and Standard
  (S1–S3) if the configuration fits the target tier and the region has
  capacity. Other tier changes need a new service and a re-index.
- **Semantic ranker** availability depends on tier and region. The standard
  plan bills semantic requests beyond the free monthly allowance; budget for
  it.
- For a private endpoint, provide an existing same-region subnet and an existing
  `privatelink.search.windows.net` zone with a VNet link. Validate routing, DNS
  resolution from the app and subnet policies. Clients keep using the public
  endpoint name, which resolves to the private address. With public access
  disabled, portal access to index data needs a browser inside the network.
  Indexers that pull from private data sources need shared private links,
  which are outside this composition.
- The production lock covers the search service and is inherited by its role
  assignments. Rotating a principal in production therefore needs a reviewed
  lock removal. A Bicep incremental deployment also leaves a previous
  assignment in place: remove stale grants explicitly. The lock does **not**
  block updates or an actor who may remove locks. Terraform destroy removes its
  own lock first; operator approvals must deny unreviewed destroy, replacement
  and lock removal.
- Diagnostics need an existing Log Analytics workspace (required in
  production). `OperationLogs` records queries and indexing operations; its
  ingestion and retention are billed by the workspace. Delete the diagnostic
  setting before deleting or re-creating the service with the same name.
- Register `Microsoft.Search` and confirm the region offers the tier, replicas
  and semantic ranker.
- The guards accept only Azure public-cloud private DNS zones, by exact ARM ID
  shape and casing, and a `Microsoft.Network/virtualNetworks/*/subnets/*`
  subnet ID.

## Offline checks and pins

Checked tool baseline: **Bicep 0.39.26** and **Terraform 1.11.3**. Terraform
pins **Azure/azapi 2.13.0**. API versions: `Microsoft.Search` 2025-05-01,
`Microsoft.Network` 2025-01-01, role assignments 2022-04-01, locks 2020-05-01
and `Microsoft.Insights/diagnosticSettings` 2021-05-01-preview (the version AVM
and the sibling compositions use). These are the newest GA versions in the
local Bicep type index. A newer GA Search management API exists but is not yet
in that index. Adopt it as a separate reviewed change with a matching Bicep
upgrade. No external modules, restore or provider download.

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
revert inputs through the owning IaC tool and review the plan. Deleting the
service deletes its indexes; rebuild them from the source data. Replaced
services, private DNS records, removed grants and lock removals cannot be
undone by a source revert. Omitting the workspace input in dev/test makes
Terraform delete the diagnostic setting; a Bicep incremental deployment leaves
it in place, so delete it explicitly. Logs already ingested stay in the
workspace for its retention period. Never switch Bicep/Terraform ownership by
applying the other source; review import and state migration first.

## Sources

Checked while authoring:

- [Enable role-based access and disable API keys](https://learn.microsoft.com/en-us/azure/search/search-security-enable-roles)
  and [built-in roles for AI Search](https://learn.microsoft.com/en-us/azure/search/search-security-rbac)
  (role IDs, 5–10 minute propagation).
- [Reliability in AI Search](https://learn.microsoft.com/en-us/azure/reliability/reliability-ai-search)
  (SLA: two replicas read-only, three read-write; zone distribution).
- [Choose a pricing tier](https://learn.microsoft.com/en-us/azure/search/search-sku-tier)
  and [service limits](https://learn.microsoft.com/en-us/azure/search/search-limits-quotas-capacity)
  (Basic and Standard switching, Basic replica limit).
- [Enable or disable semantic ranker](https://learn.microsoft.com/en-us/azure/search/semantic-how-to-enable-disable)
  (free plan by default, standard plan for continued access).
- [Create a private endpoint](https://learn.microsoft.com/en-us/azure/search/service-create-private-endpoint)
  (`searchService` sub-resource, `privatelink.search.windows.net`).
- [Monitor AI Search](https://learn.microsoft.com/en-us/azure/search/monitor-azure-cognitive-search)
  and [supported resource logs](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-logs/microsoft-search-searchservices-logs).
- [Security baseline](https://learn.microsoft.com/en-us/security/benchmark/azure/baselines/azure-cognitive-search-security-baseline)
  and [built-in roles reference](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/ai-machine-learning).
- [Search service schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.search/2025-05-01/searchservices),
  [role assignment schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2022-04-01/roleassignments),
  [private endpoint schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2025-01-01/privateendpoints),
  [lock schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2020-05-01/locks)
  and [diagnostic-settings schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.insights/2021-05-01-preview/diagnosticsettings).
- [Terraform azapi_resource 2.13.0](https://registry.terraform.io/providers/Azure/azapi/2.13.0/docs/resources/resource).
