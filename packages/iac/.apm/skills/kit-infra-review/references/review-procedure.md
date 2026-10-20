# Infrastructure review procedure in depth

An infrastructure change rarely lives in one file type. A single pull request
can change Terraform or Bicep, a pipeline, a container image, and telemetry.
Review each layer with its specialist skill, then judge the combined risk.

## 1. Scope the change

Record before reading any diff:

- Environments and accounts or subscriptions affected, and their owners.
- State backends, workspaces, deployment stacks, or resource groups touched.
- Identities the pipeline uses to plan, preview, and apply.
- Whether the change can run from a fork or untrusted trigger.
- Data-bearing resources (databases, storage, key stores, queues) in scope.

## 2. Collect artifacts, not access

Ask the operator for rendered, read-only artifacts and their provenance:

| Layer | Artifact | Produced by |
| --- | --- | --- |
| Terraform | `plan.json`, saved plan checksum | `terraform show -json tfplan` |
| Bicep / ARM | `whatif.json` with full payloads | `az deployment ... what-if --result-format FullResourcePayloads` |
| CI | Changed workflow files | Repository diff |
| Containers | Dockerfile, build context listing, scan report, SBOM | Build pipeline |
| Observability | Collector config, synthetic samples, alert rules | Local run, `promtool` |

Record each artifact's command, tool versions, and SHA-256. The reviewer does
not authenticate to production to produce them.

## 3. Layered checks

Run each layer with its specialist skill (by name, from the same capability
package):

| Layer | Skill | Key mechanical check |
| --- | --- | --- |
| Terraform | `kit-terraform-validation` | `review_plan.py --file plan.json` |
| Bicep / ARM | `kit-azure-validation` | `review_whatif.py --file whatif.json` |
| Workflows | `kit-ci-review` | `check_workflow_permissions.py .github/workflows` |
| Images | `kit-containers` | Hadolint, image scan, digest pins |
| Telemetry | `kit-observability` | Collector validate, `promtool check rules` |

A mechanical check that exits non-zero is a finding, not a failure of the
review. Malformed input (exit 2 from the plan and what-if reviewers) stops
the review until the artifact is regenerated.

## 4. Classify risk per resource

| Class | Examples | Required before acceptance |
| --- | --- | --- |
| Destructive | Delete, replace, recreate, complete-mode removal, stack `deleteResources` | Owner approval, backup or recovery plan, maintenance window if user-facing |
| Access-widening | New role assignment, broader scope, public network access, new federated credential, `id-token: write` | Security owner approval and least-privilege justification |
| Ownership change | `moved`, `import`, `removed`, state moves, stack detach | Owner of both old and new state confirms |
| Supply-chain | New action, image, module, or provider; version bump | Pin to SHA, digest, or exact version; changelog read |
| Operational | Alert, SLO, sampling, retention change | Service owner acknowledgment |
| Benign | Tag change, description, scaling within limits | Reviewer acceptance |

## 5. Cross-layer questions

- Does the pipeline identity hold more privilege than the plan needs?
- Can the workflow that applies this change be triggered by untrusted input?
- Will the new or replaced resource emit telemetry and be covered by alerts
  from day one?
- Does an image or module version change alter what the infrastructure
  template deploys without a template diff?
- Is rollback possible? Replacements of data-bearing resources are often
  irreversible without a restore.

## 6. Decide and hand off

- Accept, accept with conditions, or reject, per resource class.
- Hand apply, deploy, and rollback to the named operator with the evidence
  bundle; never apply during review.
- List skipped checks and why, so the next reviewer knows what was not seen.

## Sources

- <https://developer.hashicorp.com/terraform/cli/commands/plan>
- <https://learn.microsoft.com/azure/azure-resource-manager/templates/deploy-what-if>
- <https://docs.github.com/en/actions/reference/security/secure-use>
- <https://learn.microsoft.com/azure/well-architected/operational-excellence/safe-deployments>
