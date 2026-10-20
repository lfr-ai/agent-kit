# Acceptance gates for infrastructure changes

Use this matrix to decide whether a change is ready for the operator. A gate
is met only with evidence recorded in the
[evidence record](../assets/templates/infrastructure-evidence-template.md).

## Universal gates

| Gate | Evidence |
| --- | --- |
| Artifacts are operator-produced with recorded commands and checksums | Evidence record "Artifacts" section |
| All mechanical checks ran, or each skipped check has a reason | Command outputs and exit codes |
| Every destructive change has owner approval and a recovery plan | Per-resource risk table |
| Every access-widening change has security owner approval | Per-resource risk table |
| No secrets in source, parameters, logs, images, or artifacts | Reviewer statement plus scanner output |
| Apply, deploy, and rollback are assigned to a named operator | Hand-off section |

## Layer gates

| Layer | Gate | Mechanical evidence |
| --- | --- | --- |
| Terraform | Versions constrained, lock file committed, modules pinned | Static pipeline log |
| Terraform | fmt, validate, test, TFLint, security scan pass | CI run link or local output |
| Terraform | Plan reviewer exit 0, or 3/4 with approvals | `review_plan.py` JSON summary |
| Bicep | Build, lint, `build-params` pass for every environment | CLI output |
| Bicep | What-if with full payloads at recorded scope | `whatif.json` checksum |
| Bicep | What-if reviewer exit 0, or 3/4 with approvals | `review_whatif.py` JSON summary |
| CI | Workflow checker exit 0 or approved exceptions | `check_workflow_permissions.py` output |
| CI | Deploys behind protected environments with OIDC | Workflow diff and environment settings |
| Containers | Bases pinned by digest; non-root; exec-form entrypoint | Hadolint output |
| Containers | SBOM, provenance, scan gate present | Build log or attestation |
| Observability | New resources emit telemetry and are covered by alerts | Collector config, alert rules |
| Observability | Alert rules pass `promtool check rules` and tests | `promtool` output |

## Decision outcomes

- **Accept**: every applicable gate met.
- **Accept with conditions**: non-destructive gaps with a named owner and a
  due date (for example, adding a missing alert after deployment). Never use
  this outcome for destructive or access-widening gaps.
- **Reject**: malformed artifacts, unapproved destructive or access-widening
  changes, secrets exposure, or unpinned supply-chain inputs.

## Sources

- <https://learn.microsoft.com/azure/well-architected/operational-excellence/safe-deployments>
- <https://developer.hashicorp.com/terraform/tutorials/automation/automate-terraform>
- <https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment>
