# Azure Container Apps alerts (opt-in)

Two focused metric alerts for an **existing** Container App: replica restarts
and HTTP 5xx responses. Prefer a caller-owned Azure Monitor action group with
Teams and optionally email receivers; email-only can create a group here.
Choose **one** canonical implementation:
[Bicep](bicep/main.bicep) **or** [Terraform](terraform/main.tf), never both
over the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Reference `bicep/main.bicep` as a
resource-group-scoped module or `terraform` as a local Terraform child module.
The caller owns the resource group, the Container App, the Teams workflow,
provider authentication and state.

## What is included

| Part | Reason |
| --- | --- |
| Action group | Reuse an existing group by ID, or create one with email receivers. No Teams webhook secret enters this stack. |
| Restart alert | A replica restarted more than 3 times (`RestartCount` maximum): crash loop or failing probes. |
| 5xx alert | More than 5 HTTP 5xx responses in 5 minutes (`Requests`, `statusCodeCategory` = `5xx`). Needs ingress. |
| Input guards | Exactly one of email receivers, an existing group ID, or explicit dev/test-only `unmonitored=true`. Invalid or conflicting destinations fail. |

Metric alerts evaluate every minute over 5 minutes at severity 2 (Warning) and
resolve themselves when the signal clears. A "no replicas" alert is
deliberately not included; [REFERENCE.md](REFERENCE.md) explains when to add
one. CPU and memory alerts are not included either: the Container Apps
percentage metrics (`CpuPercentage`, `MemoryPercentage`) are still preview, and
the absolute `UsageNanoCores` and `WorkingSetBytes` need a per-app threshold.
Add them from the output action group once a sizing baseline exists.

## Inputs

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Required | Meaning |
| --- | --- |
| `namePrefix` | 2–32 lowercase letters/digits/single hyphens; start with letter, end alphanumeric. The first 12 characters become the action group short name. |
| `stage` | `dev`, `test`, `staging`, `prod`; separate prefixes/groups/state per stage |
| `containerAppResourceId` | ARM ID of the existing app, canonical casing (`/subscriptions/…/resourceGroups/…/providers/Microsoft.App/containerApps/…`) |
| `resource_group_id` | Terraform only: existing resource group ARM ID for the alert resources |

Supply `emailReceivers` (empty list by default), or
`existingActionGroupResourceId` (omitted, null, by default; an empty string is
rejected). Supplying the
existing group ID creates **only the two alerts**: no action group resource,
data-source read, receiver configuration or webhook URL enters this stack.
The operator configures and tests email, Teams, Logic Apps or other receivers in
that existing group. Inline receivers and an existing group ID are mutually
exclusive. This is the preferred path for a workflow that uploads preview files.

`unmonitored` defaults to false. Set it explicitly only for dev/test without
notifications. This standalone module then creates the two rules with empty
actions and no group. The starter's `alertsUnmonitored` /
`alerts_unmonitored` instead skips the entire notification module. Teams
workflow authorization, connections and co-owners stay in the operator's setup.

| Stage | Receivers | Alert rules |
| --- | --- | --- |
| `dev`, `test` | Email or existing group, or explicit `unmonitored=true` | Two metric rules; empty actions only with opt-out |
| `staging`, `prod` | Email or existing group with operator-verified receivers; opt-out rejected | Two metric rules |

Output: the action group ID, or null with `unmonitored=true`.
An existing group is not imported, modified or deleted by this module.

The [Azure bootstrap](../../docs/bootstrap.md) grants Reader only, which is
**insufficient** to create alerts or action groups. The operator grants scoped
alert-write and referenced-resource access separately.

## Verify and adopt

From the repository root using installed tools:

```powershell
uv run --locked pytest tests\integration\delivery\infra\test_container_apps_alerts.py -q
```

The tests use the installed pinned Bicep/Terraform toolchain and the
**Azure/azapi 2.13.0** pin. Full Terraform validation reuses
the `CONTAINER_APPS_AZAPI_MIRROR` provider mirror. Missing tools or providers
are skips, not live validation.

Before adoption, rollback is removal of these sources and their test. After
adoption, notifications already sent, alert history and the Teams workflow are
not undone by a source revert.
Terraform includes a `moved` block from `azapi_resource.notify` to
`azapi_resource.notify[0]`, preserving the owned group's identity when the new
input stays omitted. Switching an already deployed stack to an existing group is
an ownership change: Terraform plans removal of its old owned group; Bicep
incremental deployment leaves it behind. Review that transition rather than
assuming the same ID automatically transfers ownership.
The legacy inline webhook input and the speculative Resource Health rule were
removed. Existing pinned consumers keep their old implementation until a reviewed
upgrade. Terraform will plan removal of the old health rule; incremental Bicep
leaves it behind for explicit operator cleanup. Before upgrading an inline Teams
group, move receiver ownership deliberately; do not let an apply silently remove
the only working destination.
See [operator gates, Teams setup, rollback and sources](REFERENCE.md).
