# Plan review and drift

## Produce reviewable plan artifacts

The operator, not the reviewer, runs these commands in an approved
environment with the declared Terraform and provider versions:

```shell
terraform init -backend-config=environments/dev/backend.hcl
terraform plan -lock-timeout=5m -detailed-exitcode \
  -var-file=environments/dev/terraform.tfvars -out=tfplan
terraform show -json tfplan > plan.json
sha256sum tfplan plan.json
```

`-detailed-exitcode` returns 0 for no changes, 2 for changes, and 1 for
errors. Apply only the saved `tfplan`; a fresh `apply` re-plans and may differ
from what was reviewed. Saved plans and their JSON contain sensitive values in
clear text: store them only where state may be stored, and delete them after
apply.

## Read the JSON

| Field | Meaning |
| --- | --- |
| `format_version` | JSON schema version; the reviewer accepts 1.x |
| `resource_changes[].change.actions` | `no-op`, `create`, `read`, `update`, `delete`, or a two-element replace |
| `resource_changes[].action_reason` | Why an action was chosen, for example `replace_because_cannot_update`, `delete_because_no_resource_config` |
| `resource_changes[].change.replace_paths` | Attributes forcing replacement |
| `resource_changes[].previous_address` | Present when a `moved` block applied |
| `resource_changes[].change.importing` | Present when an `import` block applies |
| `resource_drift` | Differences between state and real infrastructure found during refresh |
| `output_changes` | Root output changes |
| `errored`, `complete`, `deferred_changes` | Incomplete plans that must not be approved |

Replacement order matters: `["delete", "create"]` causes downtime;
`["create", "delete"]` comes from `create_before_destroy` and briefly runs both.
Either order destroys the original object and its data.

## Review steps

1. Confirm the plan's backend, workspace, and variable file match the target.
2. Run [the plan reviewer](../assets/review_plan.py) with `--file plan.json`.
   Exit 2 rejects malformed or incomplete input, 3 lists deletes, 4 lists
   replacements. No flag approves a destructive change.
3. For each delete or replace, read `action_reason` and `replace_paths`.
   A replace caused by an immutable attribute (name, location, SKU tier) is
   intended only when the change requested it.
4. Inspect `resource_drift`. Drift means someone changed infrastructure out of
   band; decide whether to adopt it into configuration or let the plan revert
   it, and record the decision.
5. Check identity, role assignment, network rule, and key vault access policy
   changes individually; they rarely look destructive but widen access.
6. Confirm `moved`, `import`, and `removed` operations appear as intended and
   produce no extra changes.

## Drift detection

- `terraform plan -refresh-only` shows only drift between state and reality,
  without proposing configuration changes. Run it on a schedule with
  `-detailed-exitcode` and alert on exit code 2.
- `terraform apply -refresh-only` updates state to match reality; it is an
  operator decision that accepts the drift.
- `-refresh=false` hides drift. Do not accept plans generated with it unless
  the reason is recorded.

## Sources

- <https://developer.hashicorp.com/terraform/cli/commands/plan>
- <https://developer.hashicorp.com/terraform/internals/json-format>
- <https://developer.hashicorp.com/terraform/cli/commands/show>
- <https://developer.hashicorp.com/terraform/tutorials/state/resource-drift>
- <https://developer.hashicorp.com/terraform/language/meta-arguments/lifecycle>
