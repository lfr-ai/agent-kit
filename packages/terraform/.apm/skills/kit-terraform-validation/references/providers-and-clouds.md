# Providers, clouds, and OpenTofu

The review procedure is the same for every cloud: pinned providers, remote
state with locking, federated credentials, offline static checks, and a
reviewed plan JSON. This reference lists what differs per cloud and per CLI.
Versions and support facts were checked in 2026-10.

## Provider pinning

| Provider | Source | Latest checked | Suggested constraint |
| --- | --- | --- | --- |
| Azure | `hashicorp/azurerm` | 5.11.0 | `~> 5.0` for new work; the Azure blueprint still pins `~> 4.0`, so plan a major upgrade deliberately |
| AWS | `hashicorp/aws` | 6.70.0 | `~> 6.0` |
| Google Cloud | `hashicorp/google` | 8.8.1 | `~> 8.0` (add `hashicorp/google-beta` only for beta-only resources) |

- Constrain to one major version and let the committed `.terraform.lock.hcl`
  fix the exact build. Record hashes for every platform CI and developers use.
- Upgrade one provider major version at a time, read its upgrade guide, and
  review the plan for replacements caused by changed defaults.
- Provider configuration lives only in root modules; modules declare
  `required_providers` and, for aliases, `configuration_aliases`.

## Credentials in CI

Use short-lived federated credentials from the CI provider's OIDC token; never
store cloud keys as repository secrets. Workflow mechanics (environments,
approvals, subject claims) belong to `kit-delivery-pipelines`; the review only
checks that the plan identity is read-scoped.

| Cloud | GitHub step | Terraform reads |
| --- | --- | --- |
| Azure | none required, or `azure/login` for the CLI | `ARM_USE_OIDC=true`, `ARM_CLIENT_ID`, `ARM_TENANT_ID`, `ARM_SUBSCRIPTION_ID` |
| AWS | `aws-actions/configure-aws-credentials` with `role-to-assume` | Standard AWS environment credentials exported by the step |
| Google Cloud | `google-github-actions/auth` with `workload_identity_provider` (direct Workload Identity Federation preferred) | Application Default Credentials file exported by the step |

- Plan identities need read access to resources plus lock rights on the state
  backend. Apply identities are separate and bound to a protected environment.
- Pin `allowed_account_ids` (AWS) or the subscription and project in provider
  configuration so a mis-scoped identity fails before planning.

## Remote state backends

| Backend | Locking | Encryption at rest | Notes |
| --- | --- | --- | --- |
| `azurerm` | Native blob lease | Storage service encryption; optional customer managed key on the account | Use `use_azuread_auth = true` and data-plane roles, not account keys. Enable blob versioning and soft delete. |
| `s3` | `use_lockfile = true` writes a `<key>.tflock` object with conditional writes | `encrypt = true` (SSE-S3) or `kms_key_id` (SSE-KMS) | S3-native locking arrived as an opt-in in Terraform 1.10 and became generally available in 1.11, which also deprecated the DynamoDB arguments (`dynamodb_table`); OpenTofu added it in 1.10. Enable bucket versioning. |
| `gcs` | Native | Google-managed by default; `kms_encryption_key` (CMEK) or `encryption_key` (customer-supplied) | Enable object versioning. Keep KMS keys until every state object was rewritten with the new key. |

Migrating an S3 backend from DynamoDB to native locking: set both
`use_lockfile = true` and `dynamodb_table` for one release cycle so every
runner takes both locks, then remove `dynamodb_table` and delete the table
after no run uses it.

Blueprints: [Azure dev backend](../assets/blueprint/environments/dev/backend.hcl.template),
[AWS backend](../assets/blueprint/aws/backend.hcl.template),
[Google Cloud backend](../assets/blueprint/gcp/backend.hcl.template).

## State encryption choices

| Approach | Protects against | Limits |
| --- | --- | --- |
| Backend-side (SSE-S3 or SSE-KMS, Azure Storage encryption, GCS CMEK) | Media loss and storage-level access without the key | Anyone who can read the object through the API reads plain state |
| OpenTofu native encryption (1.7 and later) | Anyone reading the state or plan object without the encryption key, including storage administrators | OpenTofu only; Terraform cannot read the result. Losing the key loses the state. Configure a fallback key for rotation and back up keys. |

OpenTofu encryption is configured in an `encryption` block inside `terraform`
or through `TF_ENCRYPTION`, with key providers such as PBKDF2 passphrases,
AWS KMS, Google Cloud KMS, Azure Key Vault, or OpenBao. Enabling it on an
existing state requires a migration with an unencrypted fallback; follow the
official initial setup steps. Neither approach replaces least-privilege access
to the state store, and both still require `sensitive`, `ephemeral`, and
write-only arguments to keep secrets out of state where possible.

## TFLint rulesets per cloud

Add the ruleset plugin for each provider in use next to the bundled
`terraform` ruleset, pinned to a reviewed release (latest checked 2026-10):

```hcl
plugin "aws" {
  enabled = true
  version = "0.50.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

plugin "google" {
  enabled = true
  version = "0.41.0"
  source  = "github.com/terraform-linters/tflint-ruleset-google"
}
```

The Azure ruleset is in the [TFLint template](../assets/blueprint/.tflint.hcl.template);
its latest checked release is 0.33.0. Run `tflint --init` in CI to download
plugins with the pinned versions.

## OpenTofu compatibility

| Concern | Terraform | OpenTofu |
| --- | --- | --- |
| CLI | `terraform` | `tofu` with the same subcommands (`init`, `plan`, `show -json`, `test`) |
| Plan JSON | `format_version` 1.x | Same format; the [plan reviewer](../assets/review_plan.py) accepts both |
| Files | `.tf`, `.tf.json`, `.tftest.hcl` | Also `.tofu` and `.tofu.json`; a `.tofu` file overrides the `.tf` file with the same base name |
| Registry | `registry.terraform.io` | `registry.opentofu.org`; `hashicorp/aws` resolves there |
| Lock file | `.terraform.lock.hcl` | Same file name; hashes differ by registry, so regenerate when switching |
| Hosted runs | HCP Terraform, Terraform Enterprise | TACOS platforms or self-hosted CI |
| CI setup | `hashicorp/setup-terraform` | `opentofu/setup-opentofu` with `tofu_version` and `tofu_wrapper: false` |

Pin one CLI per root module. Use `.tofu` files only for OpenTofu-only features
in modules that must keep working with Terraform. The
[OpenTofu plan workflow](../assets/blueprint/github/tofu-plan.yml.template)
mirrors the Terraform workflow; migration steps and caveats are owned by
`kit-iac-selection`.

## Cloud blueprints

| Template | Destination | Purpose |
| --- | --- | --- |
| [versions.tf](../assets/blueprint/aws/versions.tf.template) | `infra/aws/versions.tf` | AWS provider pin, partial S3 backend |
| [providers.tf](../assets/blueprint/aws/providers.tf.template) | `infra/aws/providers.tf` | Region, allowed account, `default_tags` |
| [backend.hcl](../assets/blueprint/aws/backend.hcl.template) | `infra/aws/environments/<env>/backend.hcl` | S3 state with `use_lockfile` |
| [main.tf](../assets/blueprint/aws/main.tf.template) | `infra/aws/main.tf` | Private, encrypted, versioned, TLS-only bucket |
| [variables.tf](../assets/blueprint/aws/variables.tf.template) | `infra/aws/variables.tf` | Typed, validated inputs |
| [outputs.tf](../assets/blueprint/aws/outputs.tf.template) | `infra/aws/outputs.tf` | Bucket name and ARN |
| [versions.tf](../assets/blueprint/gcp/versions.tf.template) | `infra/gcp/versions.tf` | Google provider pin, partial GCS backend |
| [providers.tf](../assets/blueprint/gcp/providers.tf.template) | `infra/gcp/providers.tf` | Project, region, `default_labels` |
| [backend.hcl](../assets/blueprint/gcp/backend.hcl.template) | `infra/gcp/environments/<env>/backend.hcl` | GCS state bucket and prefix |
| [main.tf](../assets/blueprint/gcp/main.tf.template) | `infra/gcp/main.tf` | Uniform access, public access prevention, versioning |
| [variables.tf](../assets/blueprint/gcp/variables.tf.template) | `infra/gcp/variables.tf` | Typed, validated inputs and label rules |
| [outputs.tf](../assets/blueprint/gcp/outputs.tf.template) | `infra/gcp/outputs.tf` | Bucket name and URL |

## Review checklist

- [ ] Each provider is constrained to one major version; lock file committed.
- [ ] CI uses federated credentials; plan and apply identities differ.
- [ ] Backend locking is native (`use_lockfile`, blob lease, GCS); no new
      DynamoDB lock tables.
- [ ] State encryption approach is recorded, with key backup and rotation.
- [ ] TFLint ruleset for every provider in use is enabled and pinned.
- [ ] The CLI (Terraform or OpenTofu) is pinned per root module in CI.

## Sources

- <https://registry.terraform.io/providers/hashicorp/aws/latest/docs>
- <https://registry.terraform.io/providers/hashicorp/google/latest/docs/guides/provider_reference>
- <https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs>
- <https://developer.hashicorp.com/terraform/language/backend/s3>
- <https://developer.hashicorp.com/terraform/language/backend/gcs>
- <https://developer.hashicorp.com/terraform/language/backend/azurerm>
- <https://developer.hashicorp.com/terraform/language/upgrade-guides>
- <https://developer.hashicorp.com/terraform/language/files/dependency-lock>
- <https://opentofu.org/docs/language/state/encryption/>
- <https://opentofu.org/docs/language/files/>
- <https://opentofu.org/docs/language/settings/backends/s3/>
- <https://github.com/opentofu/setup-opentofu>
- <https://github.com/aws-actions/configure-aws-credentials>
- <https://github.com/google-github-actions/auth>
- <https://github.com/terraform-linters/tflint-ruleset-aws>
- <https://github.com/terraform-linters/tflint-ruleset-google>
- <https://github.com/terraform-linters/tflint-ruleset-azurerm>
- <https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect>
