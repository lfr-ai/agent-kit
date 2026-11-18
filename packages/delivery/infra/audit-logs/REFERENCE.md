# Audit logs: operator gates, validation and sources

Start with the [consumer contract](README.md).

## Defaults this composition relies on

The sources declare only what differs from the platform default. They
deliberately **do not restate** that activity log alerts are enabled and have
no extra conditions on service, region or Service Health event type, so the
Service Health alert covers every class for the whole subscription. The alert
`location` is declared as `global` (also the default) so a caller's azapi
`default_location` cannot move it, and `enabled: true` is declared on each
diagnostic-setting log entry because this API version requires it. The
diagnostic setting has no `logAnalyticsDestinationType`: the Activity Log
always lands in the `AzureActivity` table.

## Operator gates and ownership

- The workspace and action group already exist. The workspace owner accepts
  the retention cost: Activity Log data has no ingestion charge, but retention
  past 90 days is billed.
- The deploying identity needs, on the audited **subscription**,
  `Microsoft.Insights/diagnosticSettings/write` (for example Monitoring
  Contributor) and, for Bicep, `Microsoft.Resources/deployments/write` for the
  nested subscription deployment; in the resource group it needs
  `Microsoft.Insights/activityLogAlerts/write`; and it needs access to the
  workspace, which may sit in another subscription.
- Each resource, including a subscription, holds at most five diagnostic
  settings, and ARM rejects a second setting that sends the same category to
  the same workspace. If a platform team already exports the Activity Log (for
  example through Azure Policy), adopt or remove that setting first instead of
  deploying a duplicate. A management-group
  setting that exports the same events to the same workspace also duplicates
  them; Microsoft recommends keeping the subscription-level setting.
- The access change alert only sees changes made at subscription scope or
  below. Assignments at management-group or tenant scope, Microsoft Entra
  directory roles and Privileged Identity Management activations are in other
  logs.
- An activity-log alert fires once per matching event. Expect one notification
  per role or policy change, and treat a burst during a planned deployment as
  normal.
- Service Health covers Azure platform events, not application availability.
  The separate container-apps-alerts module monitors restart and HTTP 5xx metrics;
  it supplies no Resource Health coverage guarantee.

## Microsoft Entra ID sign-in and audit logs

Sign-in and directory audit logs are tenant-level, so this subscription-scoped
composition does not create them. This is a **privileged, manual operator
step**:

1. Sign in to the Microsoft Entra admin center as at least a **Security
   Administrator** (Attribute Log Administrator for custom security attribute
   logs).
2. Browse to **Entra ID > Monitoring & health > Diagnostic settings** and add
   a diagnostic setting.
3. Select `AuditLogs` and the sign-in categories you need (`SignInLogs`,
   `NonInteractiveUserSignInLogs`, `ServicePrincipalSignInLogs`,
   `ManagedIdentitySignInLogs`), and send them to the same workspace.

Some categories need a Microsoft Entra ID P1 or P2 license; check the current
category list before selecting. The setting applies to the whole tenant: agree
on one owner, record it with the platform team, and do not create a second
setting that sends the same categories to the same workspace.

## Offline checks and pins

Use the repository's installed pinned Bicep/Terraform toolchain. Terraform
pins **Azure/azapi 2.13.0**. API versions: `Microsoft.Insights/activityLogAlerts`
2020-10-01 (newest GA in the local Bicep type index) and
`Microsoft.Insights/diagnosticSettings` 2021-05-01-preview (no GA version
exists; the same version the other delivery compositions and AVM use). The
Bicep source uses one local subscription-scope file, `activity-log.bicep`,
because a resource-group deployment cannot declare a subscription resource
directly. No external modules, restore or provider download.

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
revert inputs through the owning IaC tool and review the plan. Turning
`alertOnAccessChanges` off makes Terraform delete the rule; a Bicep incremental
deployment leaves it in place, so delete it explicitly. Removing the
composition stops new exports, but events already in the workspace stay for
its retention period, and notifications already sent cannot be recalled. The
Entra ID diagnostic setting is removed by hand by the same role that created
it. Never switch Bicep/Terraform ownership by applying the other source;
review import and state migration first.

## Sources

Checked while authoring this composition:

- [Activity log in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log)
  (90-day platform retention, no ingestion charge, `AzureActivity` table) and
  the [event schema and categories](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log-schema).
- [Diagnostic settings in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/data-collection/diagnostic-settings)
  and the [diagnostic-settings schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.insights/2021-05-01-preview/diagnosticsettings).
- [Service Health alerts with a Resource Manager template](https://learn.microsoft.com/en-us/azure/service-health/alerts-activity-log-service-notifications-arm),
  [types of Azure Monitor alerts](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-types)
  and the [activity log alert schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.insights/2020-10-01/activitylogalerts).
- [Integrate Microsoft Entra logs with Azure Monitor logs](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/howto-integrate-activity-logs-with-azure-monitor-logs),
  [configure Microsoft Entra diagnostic settings](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/howto-configure-diagnostic-settings)
  and [Microsoft Entra data retention and licensing](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/reference-reports-data-retention).
