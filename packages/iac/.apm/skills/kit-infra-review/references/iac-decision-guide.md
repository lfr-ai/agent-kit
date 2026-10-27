# IaC decision guide

Use this guide to compare tools on the same criteria and to rule out options
that fail a hard constraint. Product facts were verified in 2026-10 against
the sources listed at the end; re-check release and licensing pages before a
decision depends on them.

## Current landscape (verified 2026-10)

| Tool | Latest release checked | License | Clouds | State or history |
| --- | --- | --- | --- | --- |
| Terraform | 1.17.0 | BUSL-1.1 (since 1.6) | Any with a provider | Backend you choose, or HCP Terraform |
| OpenTofu | 1.13.2 | MPL-2.0 (Linux Foundation) | Any with a provider | Backend you choose, optional native encryption |
| Bicep / ARM | Bicep 0.48.1 | MIT (Bicep) | Azure only | Azure deployment history; deployment stacks |
| CloudFormation, SAM, CDK | CDK 2.275.0 | Apache-2.0 (CDK, SAM) | AWS only | Managed by the CloudFormation service |
| Google Infrastructure Manager | Managed service | Service terms | Google Cloud | Managed Terraform state per deployment revision |
| Pulumi | 3.272.0 | Apache-2.0 (engine) | Any with a provider | Pulumi Cloud or self-managed object storage |
| Crossplane | 2.4.3 | Apache-2.0 | Any with a provider | Kubernetes API server (etcd) |
| Terragrunt | 1.2.1 | MIT | Wraps Terraform or OpenTofu | Delegates to the wrapped tool |
| Terramate | 0.17.3 | MPL-2.0 | Wraps Terraform, OpenTofu, Terragrunt | Delegates to the wrapped tool |

Google Cloud Deployment Manager is past end of support: support stopped on
2026-03-31, new users have been blocked since 2026-06-30, and the service is
turned down after 2027-06-30. Do not choose it; plan migration to
Infrastructure Manager or another Terraform-based workflow.

## Tool profiles

### Terraform

- HCL configuration, provider plugins from the Terraform Registry, a
  `.terraform.lock.hcl` dependency lock, and `terraform plan` as the preview.
- Licensed under the Business Source License 1.1 since 1.6. Internal use is
  generally permitted, but products that compete with HashiCorp offerings are
  restricted; have legal review the license text for your use, especially if
  you embed or host Terraform for others.
- Recent additions include ephemeral values (1.10), write-only arguments
  (1.11), `terraform query` with list resources and provider actions (1.14),
  and Terraform Policy with the `-policies` flag, generally available in 1.17.
- HCP Terraform and Terraform Enterprise add remote runs, private registry,
  Sentinel and OPA policy sets, and Stacks.

### OpenTofu

- A community fork of Terraform 1.5 under MPL-2.0, governed in the Linux
  Foundation. It reads the same HCL and state format and uses its own registry
  at `registry.opentofu.org` (search at `search.opentofu.org`), which mirrors
  most public providers and modules.
- Features that Terraform does not have, by first release: native state and
  plan encryption (1.7), early evaluation of variables and locals in backend
  and module source blocks (1.8), `.tofu` file overrides (1.8), `for_each` on
  provider configurations and `-exclude` (1.9), OCI registry support and
  native S3 locking (1.10), the `enabled` meta-argument (1.11), and a
  `destroy` lifecycle argument (1.12).
- Both tools have provider-defined functions (Terraform 1.8, OpenTofu 1.7),
  but language features introduced since the fork can diverge. Treat the two
  as compatible today, not guaranteed compatible tomorrow; pin one CLI per
  root module and test before switching.

### Bicep and ARM templates

- Azure-native: no state file, because Azure Resource Manager is the source of
  truth. Preview with what-if. Day-zero support for new Azure resource types
  and API versions.
- Deployment stacks manage a set of resources as one unit, can delete or
  detach resources removed from the template, and can apply deny settings
  that block changes outside the stack.
- Not usable for other clouds. Choose it when the estate is Azure-only and the
  team prefers no state management. Review with `kit-azure-validation`.

### AWS CloudFormation, SAM, and CDK

- CloudFormation is the managed engine: templates in JSON or YAML, change sets
  as the preview, rollback on failure, drift detection per stack or resource,
  and StackSets to deploy one template across accounts and Regions.
- SAM is a CloudFormation transform with shorthand for serverless resources
  plus a CLI for local testing.
- The CDK defines stacks in TypeScript, JavaScript, Python, Java, C#, or Go and
  synthesizes CloudFormation templates; `cdk diff` and change sets are the
  preview. Review the synthesized template, not only the program.
- The IaC generator scans existing resources and produces templates for
  import into a stack or migration into a CDK app.

### Google Infrastructure Manager

- A managed service that runs Terraform configurations from a Cloud Storage
  bucket, Git repository, or local upload, keeps a revision history with
  state and logs, and offers preview deployments. Only the Terraform versions
  the service lists are supported; confirm before pinning `required_version`.
- Choose it when a team wants Google to host Terraform execution; otherwise
  run Terraform or OpenTofu in your own CI against a `gcs` backend.

### Pulumi

- Infrastructure defined in general-purpose languages (TypeScript, Python,
  Go, C#, Java) or YAML, with `pulumi preview` as the preview.
- State lives in Pulumi Cloud by default or in a self-managed backend (S3,
  Azure Blob Storage, Google Cloud Storage, PostgreSQL, local files); secrets
  in state are encrypted with a chosen provider.
- Pulumi ESC (environments, secrets, configuration) centralizes configuration
  and issues short-lived cloud credentials; it is managed with `pulumi env`.
- Strong where teams want real programming constructs and unit tests; weaker
  where reviewers expect a declarative diff they can read without running code.

### Crossplane

- A Kubernetes control plane: cloud resources and platform APIs become
  Kubernetes custom resources, reconciled continuously, so drift is corrected
  rather than reported.
- Fits platform teams already operating Kubernetes who want a self-service
  API. It moves the blast radius into the cluster: control plane availability,
  RBAC, and provider credentials become critical infrastructure.

### Orchestration: Terragrunt and Terramate

- Terragrunt wraps Terraform or OpenTofu with units and stacks
  (`terragrunt.stack.hcl`), dependency ordering, and generated backend and
  provider blocks to keep many root modules consistent.
- Terramate adds stack orchestration, change detection (run only changed
  stacks), code generation, and drift detection on top of Terraform,
  OpenTofu, or Terragrunt.
- Add one only when the number of root modules makes plain CI matrix jobs
  hard to keep consistent. Neither replaces the plan review.

## Criteria

Score each candidate 0 (fails) to 3 (strong) on every row. A 0 on a hard
constraint eliminates the option.

| Criterion | Hard constraint? | Questions |
| --- | --- | --- |
| Cloud coverage | Yes | Does it cover every cloud and SaaS API in scope, including identity and DNS? |
| Support status | Yes | Is the tool supported and released within the last year? |
| Licensing | Yes | Does the license meet company policy for internal use, embedding, and hosting? |
| Preview | Yes | Is there a reviewable preview (plan, what-if, change set, preview) produced in CI? |
| Team skills | No | Which languages and tools does the owning team already maintain? |
| State ownership | No | Who stores state, who can read it, how is it locked, backed up, and encrypted? |
| Policy integration | No | Which policy engines can evaluate source, preview, and organization boundary? |
| Ecosystem | No | Are maintained modules or constructs available (for example verified modules)? |
| Drift | No | Is drift reported, corrected, or invisible until the next change? |
| New-feature latency | No | How quickly are new cloud resource types supported? |
| Operating cost | No | Hosted service fees, runner time, and the effort to upgrade versions. |
| Exit cost | No | How hard is it to leave: state conversion, import, or rewrite? |

## Typical outcomes

| Situation | Usual choice |
| --- | --- |
| Azure-only estate, no wish to manage state | Bicep with deployment stacks |
| AWS-only estate, application teams own stacks | CDK or SAM over CloudFormation |
| Several clouds, or many SaaS providers | Terraform or OpenTofu |
| License policy rejects BUSL-1.1 | OpenTofu |
| Google Cloud with hosted execution wanted | Infrastructure Manager (Terraform) |
| Developers want general-purpose languages and tests | Pulumi or CDK |
| Kubernetes platform team building self-service APIs | Crossplane |
| Dozens of root modules with shared backend and provider blocks | Add Terragrunt or Terramate |

Record the decision with the [decision record](../assets/templates/iac-decision-record.md.template)
and the [tool matrix](../assets/templates/iac-tool-matrix.md.template).

## Sources

- <https://github.com/hashicorp/terraform/releases>
- <https://github.com/hashicorp/terraform/blob/main/LICENSE>
- <https://developer.hashicorp.com/terraform/language/stacks>
- <https://developer.hashicorp.com/terraform/policy>
- <https://github.com/opentofu/opentofu/releases>
- <https://opentofu.org/docs/language/state/encryption/>
- <https://opentofu.org/docs/language/files/>
- <https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/overview>
- <https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deployment-stacks>
- <https://docs.aws.amazon.com/cdk/v2/guide/home.html>
- <https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html>
- <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html>
- <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/what-is-cfnstacksets.html>
- <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/generate-IaC.html>
- <https://cloud.google.com/infrastructure-manager/docs/overview>
- <https://cloud.google.com/deployment-manager/docs/deprecations>
- <https://www.pulumi.com/docs/iac/concepts/state-and-backends/>
- <https://www.pulumi.com/docs/esc/>
- <https://docs.crossplane.io/latest/whats-crossplane/>
- <https://docs.terragrunt.com/features/stacks/>
- <https://terramate.io/docs/>
