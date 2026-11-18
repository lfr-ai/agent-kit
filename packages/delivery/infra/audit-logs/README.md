# Azure subscription audit logs (opt-in)

Exports the subscription **Activity Log** (who changed which Azure resource,
policy decisions, Service Health and Resource Health events) to an
**existing** Log Analytics workspace, and adds two activity-log alerts routed
to an **existing** action group: a Service Health alert and a
role-assignment/policy change alert. Choose **one** canonical implementation:
[Bicep](bicep/main.bicep) **or** [Terraform](terraform/main.tf), never both
over the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Reference `bicep/main.bicep` as a
resource-group-scoped module or `terraform` as a local Terraform child module.
The audited subscription is the one that holds that resource group. The caller
owns the resource group, workspace, action group, provider authentication and
state.

## What is included

| Part | Reason |
| --- | --- |
| Activity Log diagnostic setting `audit-activity-log` | Subscription scope. Categories `Administrative`, `Security`, `Policy`, `Alert`, `ServiceHealth` and `ResourceHealth` to the `AzureActivity` table. The platform keeps the Activity Log for 90 days only. |
| Service Health alert `audit-service-health` | Any Azure incident, planned maintenance, health advisory or security advisory that affects the subscription. |
| Access change alert `audit-access-changes` | A role assignment, policy assignment or policy exemption was successfully created, changed or deleted. On by default in `staging` and `prod`. |
| Input guards | Reject a workspace or action group name instead of its ARM ID. |

`Recommendation` (Advisor) and `Autoscale` (classic autoscale settings) are
left out because they are not audit events. Microsoft Entra ID sign-in and
audit logs are tenant-level and are **not** automated here; see
[the operator step](REFERENCE.md#microsoft-entra-id-sign-in-and-audit-logs).
Azure already creates the management events: this module exports selected
categories and adds selected notifications, not a complete audit system.
Resource-internal/data-plane operations and business/application events are also
excluded. There is no immutable retention, tamper-evidence or compliance
certification claim.

## Inputs

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Required | Meaning |
| --- | --- |
| `stage` | `dev`, `test`, `staging`, `prod` |
| `logAnalyticsWorkspaceId` | ARM ID of the existing workspace (`/subscriptions/…/providers/Microsoft.OperationalInsights/workspaces/…`) |
| `actionGroupId` | ARM ID of the caller-owned action group, for example a monitored [container-apps-alerts](../container-apps-alerts/README.md) output |
| `resource_group_id` | Terraform only: existing resource group ARM ID for the alert rules |

Optional: `alertOnAccessChanges` (`true` in `staging` and `prod`, otherwise `false`).

| Stage | Activity Log export | Service Health alert | Access change alert |
| --- | --- | --- | --- |
| `dev`, `test` | Yes | Yes | Off unless `alertOnAccessChanges` |
| `staging`, `prod` | Yes | Yes | **On** unless explicitly `false` |

Deploy **once per subscription**: the setting and rule names are fixed. If one
subscription hosts several stages, deploy it once with the strictest stage.
The starter does not deploy this module. A platform owner first checks existing
subscription/Policy exports to avoid duplication, and may reuse the diagnostic
workspace and action group only when their access and retention policies fit.
Long-term retention is owned by that workspace/storage owner and is separate
from the platform's 90-day Activity Log retention and application diagnostics.

Output: `activityLogSettingId`, the ARM ID of the diagnostic setting.

## Verify and adopt

From the repository root using installed tools:

```powershell
uv run --locked pytest tests\integration\delivery\infra\test_audit_logs.py -q
```

The tests use the same Bicep 0.39.26 / Terraform 1.11.3 baseline and
**Azure/azapi 2.13.0** pin as Container Apps. Full Terraform validation reuses
the `CONTAINER_APPS_AZAPI_MIRROR` provider mirror. Missing tools or providers
are skips, not live validation.

Before adoption, rollback is removal of these sources and their test. After
adoption, logs already in the workspace and notifications already sent are not
undone by a source revert.
See [operator gates, Entra ID logs, rollback and sources](REFERENCE.md).
