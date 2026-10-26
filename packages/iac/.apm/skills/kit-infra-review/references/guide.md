# Infrastructure review guide: gates, failure modes, and recovery

## Reference map

| Need | Reference |
| --- | --- |
| Full staged procedure, artifact table, risk classes | [Review procedure](review-procedure.md) |
| Gate matrix per layer and decision outcomes | [Acceptance gates](acceptance-gates.md) |
| Reversibility, restore points, rollback ownership | [Rollback and recovery](rollback-and-recovery.md) |
| Drift, blast radius, rollback questions, cost delta | [Drift, blast radius, and cost](drift-blast-radius-cost.md) |

Specialist skills in the same package carry the per-layer detail:
`kit-terraform-validation` (plan JSON and Terraform configuration),
`kit-azure-validation` (Bicep and what-if), `kit-ci-review` (workflows),
`kit-containers` (images), and `kit-observability` (telemetry and alerts).

## Quality gates

- All risky actions (delete, replace, recreate, state move, access widening)
  are surfaced per resource and carry explicit owner approval.
- All mechanical validators ran on operator-produced artifacts with recorded
  commands and checksums; malformed artifacts stopped the review.
- The evidence record lists skipped checks with reasons.
- Apply and rollback are assigned to a named operator.

## Failure modes

- Rendered configuration is missing provider, backend, or scope context.
- Artifacts were produced against the wrong workspace, subscription, or
  stack.
- Validators could not load modules or providers offline and silently
  skipped them.
- A pipeline change grants the apply identity broader access in the same
  pull request as the infrastructure change it applies.
- An image or module version bump changes deployed behavior with no template
  diff.

## Negative cases

- Rendered templates differ from checked-in source because of templating
  errors or uncommitted local files.
- Deployment scripts rely on credentials from environment variables that are
  absent during review, so their behavior cannot be predicted.
- A plan or what-if is regenerated after review and applied without a new
  review.

## Recovery

1. Ask the operator for the exact rendering and preview commands and the
   environment used; regenerate artifacts in an approved environment.
2. Make missing modules or providers available in an allowed sandbox and rerun
   validators where safe; otherwise record the gap.
3. For ownership issues, coordinate state import, move, or detach with the
   owners of both the source and target state.
4. Split pipeline privilege changes from the infrastructure change they
   enable so each is reviewed on its own.

## Prerequisites

- Rendered artifacts, declared tool and provider versions, and the intended
  target environment.
- Read access to changed source; no production write access is needed or
  wanted.

## Templates

- [Evidence record](../assets/templates/infrastructure-evidence-template.md)
- [Review report](../assets/templates/review-report.md.template)
- [Change-type worksheets](../assets/templates/change-type-worksheets.md.template)

## Sources

- <https://developer.hashicorp.com/terraform/language/state>
- <https://learn.microsoft.com/azure/azure-resource-manager/templates/deploy-what-if>
