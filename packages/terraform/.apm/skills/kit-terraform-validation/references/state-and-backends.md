# State, backends, locking, and refactoring blocks

## State is sensitive

Terraform state records every managed attribute, including values marked
`sensitive` and secrets returned by providers (connection strings, keys,
generated passwords). Treat state with the same controls as the secrets in it.

- Store state in a remote backend with encryption at rest, versioning or
  soft delete, and access limited to the identities that plan and apply.
- Separate state per environment (distinct storage account or bucket, and
  ideally a distinct subscription or account) so a dev identity cannot read
  or lock production state.
- Prefer `ephemeral` variables and write-only arguments (Terraform 1.10+ and
  1.11+) for secrets that should never be persisted in state or plan files.

## Backends and locking

| Backend | Locking | Notes |
| --- | --- | --- |
| `azurerm` | Native blob lease | Set `use_azuread_auth = true`; grant Storage Blob Data roles, not account keys. |
| `s3` | `use_lockfile = true` (opt-in 1.10, GA 1.11; OpenTofu 1.10) | S3-native lock file; DynamoDB locking is deprecated since 1.11. Enable bucket versioning. |
| `gcs` | Native | Enable object versioning; optional Cloud KMS key. |
| HCP Terraform / Enterprise | Native | Workspace-level runs, policies, and audit. |

- Use partial configuration: an empty `backend "azurerm" {}` block plus
  `-backend-config=environments/<env>/backend.hcl`. The file holds identifiers
  only; credentials come from the environment (OIDC or CLI login).
- Never disable locking (`-lock=false`) in automation. Use `-lock-timeout=5m`
  so concurrent runs wait instead of failing.
- `terraform force-unlock` is an operator action taken only after confirming
  the holding run is dead; record the lock ID and reason.

## Workspaces versus directories

CLI workspaces share one configuration and one backend with separate state
files. They suit short-lived copies of the same environment. For long-lived
environments with different access controls, use separate backend
configurations (one key per environment, as in the blueprint) so permissions
can differ per environment.

## Refactoring without replacement

Renaming a resource address in configuration looks like destroy-and-create
unless Terraform is told the objects are the same.

- `moved { from = ... to = ... }` records a rename or a move into or out of a
  module. Keep the block for as long as any state might still hold the old
  address; for shared modules, keep it across at least one major version.
- `import { to = ... id = ... }` adopts an existing object (1.5+). Pair it with
  `terraform plan -generate-config-out=generated.tf` to draft configuration,
  then edit the result. The plan must report the import with no unintended
  changes.
- `removed { from = ... lifecycle { destroy = false } }` stops managing an
  object without deleting it (1.7+).
- Prefer these blocks over `terraform state mv`, `state rm`, and
  `terraform import` commands: blocks are reviewed in pull requests and
  previewed by `plan`, while state commands mutate remote state immediately.

## Review checklist

- [ ] Backend is remote, encrypted, versioned, and locked.
- [ ] Each environment has its own state and access boundary.
- [ ] No credentials in backend files or variables.
- [ ] Renames use `moved`; adoptions use `import`; detachments use `removed`.
- [ ] Plan shows moves, imports, and forgets with zero unexpected changes.

Templates: [versions.tf](../assets/blueprint/versions.tf.template),
[dev backend](../assets/blueprint/environments/dev/backend.hcl.template),
[prod backend](../assets/blueprint/environments/prod/backend.hcl.template),
[moved.tf](../assets/blueprint/moved.tf.template). Per-cloud backends and
OpenTofu state encryption: [providers and clouds](providers-and-clouds.md).

## Sources

- <https://developer.hashicorp.com/terraform/language/state/sensitive-data>
- <https://developer.hashicorp.com/terraform/language/backend>
- <https://developer.hashicorp.com/terraform/language/backend/azurerm>
- <https://developer.hashicorp.com/terraform/language/backend/s3>
- <https://developer.hashicorp.com/terraform/language/state/locking>
- <https://developer.hashicorp.com/terraform/language/modules/develop/refactoring>
- <https://developer.hashicorp.com/terraform/language/import>
- <https://developer.hashicorp.com/terraform/language/resources/syntax#removing-resources>
- <https://developer.hashicorp.com/terraform/language/values/variables#exclude-values-from-state>
