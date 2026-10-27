---
name: kit-terraform-validation
description: Use when writing Terraform or OpenTofu, or reviewing a plan for destructive or ownership changes.
license: MIT
---

# Validate Terraform configuration and plans (read-only)

Review Terraform in two layers: the configuration (structure, pins, tests,
static analysis) and the plan (what will change). Never apply, import, move
state, or unlock during review. Start with the [review guide](references/guide.md).

## Procedure

1. Identify the root module, environment, backend key, and workspace under
   review. Record the declared `required_version`, provider constraints, and
   whether `.terraform.lock.hcl` is committed. Use
   [module structure](references/module-structure.md).
2. Check configuration hygiene: provider blocks only in the root module,
   registry modules pinned to exact versions, git modules pinned to full SHAs,
   and every variable typed, described, and validated where the API has
   constraints ([variables and tests](references/variables-and-tests.md)).
3. Confirm state handling with [state and backends](references/state-and-backends.md):
   remote encrypted backend with locking, separate state per environment,
   identifiers only in backend files, and no secrets in variables or outputs.
   For AWS, Google Cloud, or OpenTofu, check provider pins, federated CI
   credentials, backend locking (`use_lockfile`, blob lease, GCS), and the
   pinned CLI with [providers and clouds](references/providers-and-clouds.md).
   Plan JSON from `tofu show -json` is reviewed the same way.
4. Run the offline [static pipeline](references/static-analysis.md) or verify
   CI ran it for the same commit: `terraform fmt -check -recursive`,
   `terraform init -backend=false`, `terraform validate`, `terraform test`,
   `tflint --recursive`, and a Trivy or Checkov configuration scan.
5. Accept only an operator-produced plan JSON (`terraform show -json tfplan`)
   with its command, backend key, variable file, and checksum. Refuse plans of
   unknown origin or made with `-refresh=false` without a recorded reason.
6. Run the [plan reviewer](assets/review_plan.py):
   `python assets/review_plan.py --file plan.json`. Exit 2 stops the review;
   record the error and request a regenerated plan.
7. For every delete (exit 3) or replace (exit 4), read `action_reason` and
   `replace_paths` using [plan review](references/plan-review.md), and record a
   per-resource decision. Prefer a `moved` block over approving a rename as
   destroy and create.
8. Inspect `resource_drift`, `moved`/`import`/`removed` results, identity and
   role changes, network rules, and `output_changes`; flag anything that widens
   access or changes ownership even when not destructive.
9. When a consumer asks for a starting point, adapt the
   [blueprint](references/blueprint.md) (Azure, AWS, or Google Cloud root
   module, Terraform or OpenTofu plan workflow) and run its adoption check.
10. Produce the evidence bundle: commit, plan checksum, reviewer summary,
    per-resource risk notes, static pipeline results, skipped checks, and the
    named operator allowed to apply in which backend and workspace.

## Acceptance gates

- [ ] Version constraints present; lock file committed; module sources pinned.
- [ ] Remote backend with locking; one state per environment.
- [ ] fmt, validate, test, TFLint, and security scan passed for the commit.
- [ ] Plan reviewer exited 0, or every delete and replace carries an owner
      approval and a recovery plan.
- [ ] Drift and access-widening changes have a written decision.
- [ ] Plan JSON and saved plan are stored only where state may be stored.
- [ ] Apply is handed to the named operator with the reviewed saved plan.

## Out of scope

A plan review is not state reconciliation or apply authorization. Do not run
`apply`, `state` subcommands, `import`, or `force-unlock` during review.
