# Container Apps alerts: operator gates, validation and sources

Start with the [consumer contract](README.md).

## Destination ownership

Prefer `existingActionGroupResourceId` / `existing_action_group_resource_id`.
Leave `emailReceivers` empty and `unmonitored=false`. The rules and output use
that ID unchanged; this stack never reads, modifies or deletes its receivers.
The group may notify Teams, email, or both. For simple email-only setup, provide
email addresses instead and this module owns the group.

Exactly one choice is required. `unmonitored=true` is explicit dev/test-only
operation with no notifications; staging/prod reject it. The standalone module
still creates rules with empty actions, while the starter skips this module.
An ID passing validation proves neither existence nor working delivery.

## Signals and defaults

| Rule | Signal | Threshold | Caveat |
| --- | --- | --- | --- |
| `<prefix>-restarts` | `RestartCount`, Maximum | > 3 | Cumulative per replica, not a count of new restarts in the window. Slow restart trickles also accumulate; replacing the replica resets its count. |
| `<prefix>-5xx` | `Requests`, Total, `statusCodeCategory=5xx` | > 5 | Requires HTTP ingress and should be tuned to the app's traffic. |

Both evaluate every minute over five minutes at severity 2, with
`autoMitigate=true` explicitly set. The severity, thresholds and windows are
named once (Bicep variables `alertSeverity`, `evaluationFrequency`,
`windowMinutes`, `restartThreshold`, `serverErrorThreshold`; the Terraform
locals use the snake_case names) and the rule descriptions are generated from
them, so tuning one value keeps the description accurate.
Resolution follows Azure Monitor's stateful
metric-alert evaluation after the condition clears; it is not immediate.
All stages use the same signals. There is no tested availability guarantee.
The former Resource Health rule was removed because no reliable Container Apps
coverage was demonstrated. No zero-replicas rule is included: scale-to-zero is
valid, and a metric alert does not prove availability when data is missing.
CPU/memory alerts require an application sizing baseline rather than universal
thresholds.

Metric validation remains enabled. The namespace is inferred from the single
scoped resource; multi-resource target fields are unnecessary. Email keeps its
default schema. Action groups declare the required `enabled` and
`groupShortName`; names must be distinct per app and stage.

## Where alerts appear and how to test

1. In the Azure portal, open **Monitor > Alerts** and filter to the app/resource
   group. The rule determines when an alert appears; the selected action group's
   receivers determine who is notified. Assign an incident owner.
2. Save and enable the action group, then use its **Test** feature. Choose a
   representative metric alert and verify the intended mailbox and/or Teams
   channel actually receives it. Complete any email address validation.
3. In an isolated non-production app, generate more than five controlled 5xx
   responses in five minutes from a temporary test endpoint. Observe the metric,
   fired alert and notification. Restore the endpoint; confirm resolution after
   the condition clears. Never add a permanent public failure endpoint.
4. For restarts, use a disposable non-production revision with a deliberately
   failing start command, route no production traffic to it, and observe more
   than three restarts on a replica. Remove that revision and confirm recovery.
   The app must run long enough to emit metrics; missing data is not success.

Tests in this repository check resource shape, references and input failures
offline. They do not certify Azure ingestion, rule evaluation or Teams/email
delivery. The bootstrap's Reader role cannot create these resources: grant
scoped alert/group write permissions and referenced-resource access separately.
Keep app, rule group and action group in the same subscription unless a separate
cross-subscription access review establishes support.

## Teams setup stays outside application IaC

An operator creates the destination with the channel owner's consent. Prefer a
caller-owned action group with a **Logic Apps** action that transforms the
Azure Monitor common alert schema and posts to Teams. A Teams Workflow can also
be used through an operator-managed integration, but payload compatibility and
caller authorization must be tested; a raw Teams webhook is not a drop-in
Azure Monitor receiver.

Keep workflow connections, authorization, co-owners and any bearer URLs in that
operator-owned system. Do not put raw URLs in application parameters, Terraform
state, previews, logs or generated examples. Document rotation/revocation and
ensure ownership survives an employee leaving. No destination is invented or
selected by this module.

## Log collection is separate from alert evaluation

Application JSON stdout/stderr goes through Container Apps diagnostic settings
to Log Analytics. Use **Monitor > Logs** (or the app's **Logs**) and
`ContainerAppConsoleLogs_CL` for retained console records; filter by app,
revision and correlation IDs. Records survive container restarts and deployments
within the workspace/table retention policy. Live streaming is not historical
storage, and collection is not guaranteed lossless.

These rules use platform metrics, not log queries, and do not depend on the
workspace. Ingress HTTP logging is not enabled by default: app middleware already
provides sanitized access records. Requests failing before it executes have no
application record; platform metrics/system diagnostics offer only partial
coverage. Enable ingress logs only for an explicit diagnostic need and review
their sensitive URL fields and retention.

## Activity Log export (operator-owned)

The [audit-logs module](../audit-logs/README.md) exports selected existing Azure
Activity Log categories once per subscription. It can reuse the selected
workspace and action group, but is not deployed once per app. Audit retention and
access policy are independent decisions from ordinary application diagnostics.

## Migration and rollback

Existing pinned consumers are unchanged until they intentionally upgrade.
The legacy inline Teams input and the speculative health rule no longer exist.
Move receiver ownership and test delivery before adopting the new interface.
Never reference a formerly owned group as external without a reviewed ownership
transition: Terraform may otherwise destroy it, while incremental Bicep leaves
it behind. The retained Terraform `moved` block preserves the address transition
from `notify` to `notify[0]` for email-owned groups. Use reviewed moved/import
workflows for other changes; a source revert does not move state back.

Terraform previews deletion of the old health rule. Bicep incremental deployment
leaves it for explicit cleanup. Do not delete workspaces or retained history as
part of this change. Sent notifications, Teams posts and history cannot be undone
by rolling back sources. Removing repository files is never authorization to
destroy cloud resources.

## Sources

Reviewed against Microsoft documentation on 2026-11-16:

- [Container Apps logs and queries](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
- [Action groups, Logic Apps/Teams and testing](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/action-groups)
- [Metric alert resource contract](https://learn.microsoft.com/en-us/azure/templates/microsoft.insights/2018-03-01/metricalerts)
- [Container Apps metrics](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-metrics/microsoft-app-containerapps-metrics)
- [Alert state and resolution](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview)
