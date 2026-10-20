# Terraform blueprint index

Copy the templates into an `infra/` directory, drop the `.template` suffix,
replace example names (`orders`, `platform-team`, `cc-0000`, state account
names), and run the static pipeline before the first plan. Each file is a
starting point; the consumer owns the result.

## Root module

| Template | Destination | Purpose |
| --- | --- | --- |
| [versions.tf](../assets/blueprint/versions.tf.template) | `infra/versions.tf` | CLI and provider constraints, partial backend |
| [providers.tf](../assets/blueprint/providers.tf.template) | `infra/providers.tf` | Provider features; auth from environment |
| [variables.tf](../assets/blueprint/variables.tf.template) | `infra/variables.tf` | Typed inputs with validation |
| [locals.tf](../assets/blueprint/locals.tf.template) | `infra/locals.tf` | Naming and tag merge |
| [main.tf](../assets/blueprint/main.tf.template) | `infra/main.tf` | Resource group, module call, check block |
| [outputs.tf](../assets/blueprint/outputs.tf.template) | `infra/outputs.tf` | Non-secret outputs |
| [moved.tf](../assets/blueprint/moved.tf.template) | `infra/moved.tf` | Moved, import, removed examples |
| [root tests](../assets/blueprint/tests/main.tftest.hcl.template) | `infra/tests/main.tftest.hcl` | Offline naming and validation tests |
| [gitignore](../assets/blueprint/gitignore.template) | `infra/.gitignore` | Keep state and plans out of version control |

## Environments

| Template | Destination |
| --- | --- |
| [dev backend](../assets/blueprint/environments/dev/backend.hcl.template) | `infra/environments/dev/backend.hcl` |
| [dev inputs](../assets/blueprint/environments/dev/terraform.tfvars.template) | `infra/environments/dev/terraform.tfvars` |
| [prod backend](../assets/blueprint/environments/prod/backend.hcl.template) | `infra/environments/prod/backend.hcl` |
| [prod inputs](../assets/blueprint/environments/prod/terraform.tfvars.template) | `infra/environments/prod/terraform.tfvars` |

## Example module

| Template | Destination |
| --- | --- |
| [versions.tf](../assets/blueprint/modules/storage/versions.tf.template) | `infra/modules/storage/versions.tf` |
| [variables.tf](../assets/blueprint/modules/storage/variables.tf.template) | `infra/modules/storage/variables.tf` |
| [main.tf](../assets/blueprint/modules/storage/main.tf.template) | `infra/modules/storage/main.tf` |
| [outputs.tf](../assets/blueprint/modules/storage/outputs.tf.template) | `infra/modules/storage/outputs.tf` |
| [tests](../assets/blueprint/modules/storage/tests/storage.tftest.hcl.template) | `infra/modules/storage/tests/storage.tftest.hcl` |

## Tooling and CI

| Template | Destination |
| --- | --- |
| [TFLint](../assets/blueprint/.tflint.hcl.template) | `infra/.tflint.hcl` |
| [Trivy](../assets/blueprint/trivy.yaml.template) | `infra/trivy.yaml` |
| [terraform-docs](../assets/blueprint/.terraform-docs.yml.template) | `infra/.terraform-docs.yml` |
| [plan workflow](../assets/blueprint/github/terraform-plan.yml.template) | `.github/workflows/terraform-plan.yml` |
| [plan reviewer](../assets/review_plan.py) | `tools/review_plan.py` |

## Adoption check

1. `terraform fmt -check -recursive` passes.
2. `terraform init -backend=false && terraform validate && terraform test`
   passes in `infra/` and in each module directory.
3. `tflint --recursive` and `trivy config --config trivy.yaml .` pass.
4. The plan workflow has every `PIN_FULL_COMMIT_SHA` replaced.
5. The first real plan is reviewed with the plan reviewer before any apply.

## Sources

- <https://developer.hashicorp.com/terraform/language/modules/develop/structure>
- <https://developer.hashicorp.com/terraform/tutorials/automation/github-actions>
- <https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account>
