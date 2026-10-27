# Policy as code across clouds

Place controls at three points. A rule that must never be broken belongs at
the organization boundary, because source and preview checks can be skipped.
Positioning only: this reference helps choose tools; it does not configure
them. Versions checked 2026-10.

| Point | Purpose | Fails | Bypassed by |
| --- | --- | --- | --- |
| Before merge (source) | Fast feedback on code | The pull request | Anyone applying outside CI |
| On the preview (plan JSON, change set, what-if) | Evaluate resolved values and module output | The pipeline before apply | Local applies with write access |
| Organization boundary (cloud control plane) | Enforce on every API call, any tool | The cloud API request | Only org administrators |

## Before merge

| Tool | Scope | Notes |
| --- | --- | --- |
| TFLint with provider rulesets | Terraform and OpenTofu HCL | Ruleset plugins `tflint-ruleset-aws` (0.50.0), `tflint-ruleset-azurerm` (0.33.0), and `tflint-ruleset-google` (0.41.0) catch invalid instance types, Regions, and deprecated arguments; pin each plugin version. |
| Trivy (`trivy config`) | Terraform, plan JSON, CloudFormation, ARM, Kubernetes, Helm, Dockerfile | tfsec is now part of Trivy; prefer Trivy for new work. |
| Checkov | Terraform (AWS, Azure, Google Cloud), CloudFormation and SAM, ARM, Kubernetes, Helm, Dockerfile | Graph-based checks across resource relationships; custom checks in Python or YAML. |
| cfn-lint and CloudFormation Guard | CloudFormation and SAM templates | cfn-lint validates against the resource specification; Guard evaluates rules on JSON or YAML, including Terraform plan JSON. |
| cdk-nag | CDK apps at synth time | Rule packs run as CDK aspects, so findings fail `cdk synth`. |
| Bicep linter | Bicep | Configure rule levels in `bicepconfig.json`; see `kit-azure-validation`. |

Choose one general misconfiguration scanner (Trivy or Checkov) per
repository to avoid duplicate, conflicting suppressions. Every suppression
carries a reason, an owner, and an expiry.

## On the preview

| Tool | Input | Positioning |
| --- | --- | --- |
| OPA with Conftest | `terraform show -json` output, CloudFormation or Kubernetes YAML | Rego rules (`deny`, `warn`, `violation`) for organization-specific checks such as allowed Regions, required tags, or forbidden resource types. Portable across tools and clouds. |
| Trivy or Checkov on plan JSON | Terraform plan JSON | Resolves variables and module outputs that HCL scanning cannot see. Plan JSON holds sensitive values; scan it only on trusted runners. |
| Terraform Policy | `terraform plan -policies` | Generally available in Terraform 1.17 for `plan`, `apply`, and `query`. Terraform only; not available in OpenTofu. |
| Sentinel and OPA policy sets | HCP Terraform and Terraform Enterprise runs | Enforced between plan and apply inside the hosted service, with enforcement levels from advisory to mandatory. Only applies when runs execute there. |
| CloudFormation Hooks | CloudFormation and Cloud Control API operations | Proactive checks before provisioning, including Guard rules and AWS Control Tower proactive controls. |
| Pulumi Policies | Pulumi previews and discovered resources | Policy packs written in TypeScript or Python. |

## Organization boundary

| Cloud | Preventive | Detective and remediation |
| --- | --- | --- |
| Azure | Azure Policy with `deny` effects, assigned at management group scope; deployment stack deny settings | Azure Policy `audit`, `modify`, and `deployIfNotExists` with remediation tasks |
| AWS | Service control policies (limit principals in member accounts) and resource control policies (limit access to resources, including by external principals) in AWS Organizations; AWS Control Tower preventive controls | AWS Config rules and conformance packs; AWS Control Tower detective controls |
| Google Cloud | Organization Policy Service constraints (predefined and custom) on the organization, folder, or project | Policy Intelligence and Security Command Center findings |

Organization controls stop a change regardless of which IaC tool, console,
or script made it, so they are the only layer that protects against an
operator with direct cloud access.

## Choosing rules for each layer

1. Write the rule once in plain language with an owner, for example
   "storage must not allow public access".
2. Enforce it at the organization boundary if the cloud supports it.
3. Mirror it before merge so authors learn early, using the scanner's built-in
   check where one exists.
4. Add a preview-time rule only for what static scanning cannot see:
   computed values, cross-module relationships, and counts of destructive
   actions (the plan reviewer in `kit-terraform-validation` already fails on
   deletes and replacements).
5. Test policies like code: a passing and a failing fixture per rule.

## Review checklist

- [ ] Each must-never rule is enforced at the organization boundary.
- [ ] One general scanner per repository, pinned, with expiring suppressions.
- [ ] Provider TFLint rulesets match the clouds in use and are pinned.
- [ ] Preview-time policy runs on trusted runners against the exact plan.
- [ ] Every custom policy has a passing and a failing test fixture.

## Sources

- <https://github.com/terraform-linters/tflint-ruleset-aws>
- <https://github.com/terraform-linters/tflint-ruleset-azurerm>
- <https://github.com/terraform-linters/tflint-ruleset-google>
- <https://trivy.dev/docs/latest/guide/coverage/iac/>
- <https://github.com/aquasecurity/tfsec>
- <https://www.checkov.io/1.Welcome/What%20is%20Checkov.html>
- <https://github.com/aws-cloudformation/cfn-lint>
- <https://github.com/aws-cloudformation/cloudformation-guard>
- <https://github.com/cdklabs/cdk-nag>
- <https://www.conftest.dev/>
- <https://www.openpolicyagent.org/docs/latest/>
- <https://developer.hashicorp.com/terraform/policy>
- <https://developer.hashicorp.com/terraform/cloud-docs/policy-enforcement>
- <https://docs.aws.amazon.com/cloudformation-cli/latest/hooks-userguide/what-is-cloudformation-hooks.html>
- <https://www.pulumi.com/docs/insights/policy/>
- <https://learn.microsoft.com/en-us/azure/governance/policy/overview>
- <https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html>
- <https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_rcps.html>
- <https://docs.aws.amazon.com/config/latest/developerguide/WhatIsConfig.html>
- <https://docs.aws.amazon.com/controltower/latest/controlreference/controls.html>
- <https://cloud.google.com/resource-manager/docs/organization-policy/overview>
