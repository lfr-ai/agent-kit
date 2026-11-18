# Application Insights: operator gates, validation and sources

Start with the [consumer contract](README.md).

## Defaults this composition relies on

The sources declare only what differs from the platform default. They
deliberately **do not restate** these 2020-02-02 defaults: public network
access for ingestion and query, no ingestion sampling, IP address masking,
flow type, request source and ingestion mode (set by `WorkspaceResourceId`).
Retention is a property of the workspace tables, not of this resource. `kind`
and `Application_Type` are declared because this API version requires them.

`DisableLocalAuth` is declared in every stage (`false` in dev, `true` in test
and prod), so a redeployment reverts drift if someone re-enables
connection-string-only ingestion in test or prod.

## Why dev keeps local authentication

With local authentication enabled, anyone holding the connection string can
send telemetry to the resource. That is acceptable for a dev resource and
removes the need to grant each developer `Monitoring Metrics Publisher` just to
see local traces. The app identity is granted the role in every stage and the
deployed app always sends a token, so test, staging and prod behave like dev
for the app. If dev must be strict as well, deploy it with `stage = 'test'`: the stage
changes only this setting and the `stage` tag.

## Operator gates and ownership

- The workspace already exists and its owner accepts the ingestion cost.
  Retention, daily cap, access mode and any delete lock belong to the workspace,
  which holds the telemetry. This composition adds no lock: deleting the
  Application Insights resource does not delete telemetry already in the
  workspace.
- The app identity already exists. Pass its **object (principal) ID**. The app
  authenticates with the identity's **client** ID. The deploying identity needs
  role-assignment write on the new resource (for example Role Based Access
  Control Administrator constrained to this role).
- A new role assignment can take several minutes to apply; early telemetry
  from a fresh test, staging or prod deployment may be rejected until it does.
- Moving `logAnalyticsWorkspaceId` to another workspace sends new telemetry
  there; existing telemetry stays in the old workspace.
- Private ingestion and query (Azure Monitor Private Link Scope, AMPLS) is a
  **follow-up**, not included. It is not a per-resource setting: one AMPLS per
  network serves every Azure Monitor resource the VNet resolves, and it needs
  the scope, scoped-resource links for this component **and** the workspace, a
  private endpoint, five private DNS zones (`monitor`, `oms`, `ods`,
  `agentsvc` and `blob`) and an agreed access mode. Own it in the network
  composition, then set `publicNetworkAccessForIngestion` and
  `publicNetworkAccessForQuery` to `Disabled` here in a reviewed change.

## Offline checks and pins

Checked tool baseline: **Bicep 0.39.26** and **Terraform 1.11.3**. Terraform
pins **Azure/azapi 2.13.0**. API versions: `Microsoft.Insights/components`
2020-02-02 (newest GA) and `Microsoft.Authorization/roleAssignments`
2022-04-01. No external modules, restore or provider download.

The integration test relocates the source closure, then runs Bicep format,
lint, `build` and `build-params` for the dev and prod examples, and evaluates
every exported guard with Bicep's native parameter evaluator. Terraform runs
`fmt -check` and a contract test against the **unchanged variables.tf alone**
with the same positive and negative cases as Bicep.

Full resource validation and the mocked plans in `terraform/tests` need the
reviewed Azure/azapi 2.13.0 mirror that Container Apps uses. Set
`CONTAINER_APPS_AZAPI_MIRROR`; tests then run `terraform init -backend=false
-input=false -plugin-dir=<mirror>`. **No mirror means a reported skip, not a
provider-validation pass.** Mocks do not certify ARM behavior, policies or
permissions.

## Rollback

Before deployment, remove this directory, its integration test, its catalog
entry and the delivery README row; no cloud state has changed. After adoption,
revert inputs through the owning IaC tool and review the plan. Telemetry
already ingested stays in the workspace for its retention period. A deleted
and re-created resource gets a new connection string, so update every
consumer. Changing `principalId` makes Terraform replace the grant; a Bicep
incremental deployment leaves the previous grant in place, so remove stale
grants explicitly. Never switch Bicep/Terraform ownership by applying the
other source; review import and state migration first.

## Sources

Checked while authoring this composition:

- [Workspace-based Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/create-workspace-resource)
  and the [components schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.insights/2020-02-02/components).
- [Microsoft Entra authentication for Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/azure-ad-authentication)
  (`DisableLocalAuth`, `Monitoring Metrics Publisher`, token credential in the
  OpenTelemetry distro).
- [Connection strings](https://learn.microsoft.com/en-us/azure/azure-monitor/app/connection-strings)
  ("Ikey unique identifiers aren't security tokens or security keys";
  `APPLICATIONINSIGHTS_CONNECTION_STRING`).
- [Enable Azure Monitor OpenTelemetry](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable)
  and [Monitoring Metrics Publisher role](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/monitor#monitoring-metrics-publisher).
- [Role assignment schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2022-04-01/roleassignments).
