# Terraform review guide: gates, contracts, and recovery

Use this guide to pick the right reference and to interpret the plan
reviewer's results.

## Reference map

| Concern | Reference |
| --- | --- |
| Layout, root versus child modules, version pinning, lock file | [Module structure](module-structure.md) |
| Remote state, locking, moved/import/removed blocks | [State and backends](state-and-backends.md) |
| Validation, conditions, `terraform test`, mocks | [Variables and tests](variables-and-tests.md) |
| fmt, validate, TFLint, Trivy, Checkov, terraform-docs | [Static analysis](static-analysis.md) |
| Plan JSON fields, destructive actions, drift | [Plan review](plan-review.md) |
| Copyable starting configuration | [Blueprint index](blueprint.md) |

## Quality gates

- The plan file was produced by the operator with the declared Terraform and
  provider versions, recorded with its command and SHA-256 checksum.
- The reviewer accepts the JSON shape; nothing was silently ignored.
- No deletes or replacements, or each has a recorded, per-resource owner
  approval and a rollback or data-recovery plan.
- Provider versions are constrained, the lock file is committed, and module
  sources are pinned (exact registry version or full git SHA).
- Static pipeline (fmt, validate, test, TFLint, security scan) passed for the
  same commit.
- Drift (`resource_drift`) is explained and has a recorded decision.

## Failure modes

- Malformed or truncated JSON prevents deterministic analysis.
- The plan targeted a different workspace, backend key, or subscription.
- A provider upgrade changed defaults and turned an update into a replace.
- A renamed resource without a `moved` block appears as delete plus create.
- A plan generated with `-refresh=false` hid drift.
- A floating module reference changed between plan and apply.

## Negative cases the reviewer must reject

- Missing or non-array `resource_changes`, unsupported `format_version`.
- `errored: true`, `complete: false`, or non-empty `deferred_changes`.
- Duplicate resource addresses or duplicate JSON keys.
- Unknown `change.actions` values.

## Plan reviewer contract

[review_plan.py](../assets/review_plan.py) is a read-only stdlib reviewer.

- Input: Terraform JSON `format_version` 1.x with an explicit
  `resource_changes` array; each entry needs a unique `address` and
  `change.actions`.
- Supported actions: `no-op`, `read`, `create`, `update`, `delete`, and either
  ordering of delete/create replacement.
- Output: JSON `summary` counts and per-kind `lists` on stdout.
- Exit codes: 0 no destructive change, 2 malformed or unsupported input,
  3 deletion present, 4 replacement present. There are no approval flags.
- `--self-test` runs built-in regressions without reading files.
- It is a resource-action summary, not schema validation, a sensitive-value
  scanner, state reconciliation, or authorization to apply.

```shell
python assets/review_plan.py --file plan.json
```

## Recovery

1. Ask the operator to regenerate the plan with declared versions and record
   the exact command, backend key, and variable file.
2. If JSON is malformed, request the original `.tfplan` and rerun
   `terraform show -json` in an approved environment.
3. For replacements and deletes, require owner approval and, where data is
   involved, a verified backup or snapshot before apply.
4. Add `moved` blocks for renames instead of approving destroy and create.
5. Pin missing provider or module versions before approving destructive
   changes.

## Prerequisites

- The plan JSON produced by the operator (never a plan created by running
  untrusted code with real credentials during review).
- The declared Terraform and provider versions and the intended backend
  and workspace.

## Sources

- <https://developer.hashicorp.com/terraform/internals/json-format>
- <https://developer.hashicorp.com/terraform/cli/commands/plan>
- <https://developer.hashicorp.com/terraform/cli/commands/show>
