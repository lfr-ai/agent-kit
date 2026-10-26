# Drift, blast radius, rollback, and cost review

Reviewed 2026-10-23. Reversibility classes and restore points are detailed in
[rollback and recovery](rollback-and-recovery.md); this reference adds the
questions to ask before and around them.

## Drift

Drift is any difference between the declared configuration and the deployed
resources. A plan computed against drifted state can silently revert an
emergency fix or destroy something created by hand.

| Signal | How to see it | Decision |
| --- | --- | --- |
| Terraform refresh changes | `terraform plan -refresh-only` (operator-run) | Codify the change, or revert it deliberately |
| Bicep or ARM | What-if shows modifications to properties not in the diff | Same as above; never let a deploy revert it unnoticed |
| Resources outside state | Inventory query lists resources with no owning stack | Import, adopt into a stack, or delete with owner approval |
| Manual portal or CLI changes | Activity log entries by people | Ask why; emergency fixes must be codified within a set time |

- Resolve drift in its own reviewed change before the feature change, so the
  feature plan shows only intended differences.
- Schedule drift detection (refresh-only plans, what-if, or policy compliance)
  and route results to the owning team, not a shared inbox.

## Blast radius

Blast radius is the set of users, services, and data affected if the change
goes wrong. Review the largest plausible failure, not the expected outcome.

| Question | Smaller is better when |
| --- | --- |
| How many environments, regions, or tenants does one apply touch? | One at a time |
| Which shared resources change (DNS zones, networks, identity, shared databases)? | None, or behind a separate change |
| How many stacks or state files depend on an output that changes? | Outputs are stable or versioned |
| Does a module or provider version bump affect every consumer at once? | Consumers pin and upgrade separately |
| Can the change lock out the people who would roll it back? | Break-glass access is tested and independent |

Reduce it by splitting state per environment and component, rolling out by
ring or region, placing guardrails (resource locks, deletion protection,
`prevent_destroy`, deny assignments) on shared and data-bearing resources,
and keeping privileged changes separate from functional ones.

## Rollback review

1. Name the trigger: which alert, error rate, or check starts a rollback.
2. Name the method per layer: revert and re-apply, redeploy previous digest,
   restore from backup, or traffic switch.
3. Estimate time to roll back and compare it with the outage budget.
4. Confirm prerequisites now: backups exist, previous artifacts are retained,
   previous configuration is reloadable, operator access works.
5. Mark irreversible steps and require explicit owner acceptance.

## Cost review

| Check | Evidence |
| --- | --- |
| Estimated monthly delta at minimum, typical, and maximum scale | Pricing calculator export or a cost tool on the plan |
| New always-on resources (gateways, firewalls, dedicated hosts, reserved capacity) | Plan resource list |
| Data transfer between zones, regions, or the internet | Architecture note |
| Log and metric volume changes (ingestion and retention) | Telemetry estimate |
| Autoscale maximums and budget alerts | Config and budget rule |
| Tags that attribute cost to an owner | Plan attributes |

Cost estimates from plans are approximations; usage-based charges need a
volume assumption written next to the number.

## Anti-patterns

- Applying a plan that "only" shows drift reverts without asking who changed it.
- One state file for every environment.
- Shared module upgrades merged to all consumers in one pull request.
- Approving a change with "rollback: revert the commit" for a data migration.
- No cost owner tag, so the bill cannot be traced back.

## Primary sources

- <https://developer.hashicorp.com/terraform/tutorials/state/resource-drift>
- <https://developer.hashicorp.com/terraform/cli/commands/plan#planning-modes>
- <https://learn.microsoft.com/azure/azure-resource-manager/templates/deploy-what-if>
- <https://learn.microsoft.com/azure/azure-resource-manager/management/lock-resources>
- <https://learn.microsoft.com/azure/well-architected/operational-excellence/safe-deployments>
- <https://learn.microsoft.com/azure/cost-management-billing/costs/cost-mgt-best-practices>
- <https://learn.microsoft.com/azure/well-architected/cost-optimization/>
