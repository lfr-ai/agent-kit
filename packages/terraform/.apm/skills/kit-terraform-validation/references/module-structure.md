# Module structure and version pinning

## Standard layout

A root module is the directory where `terraform plan` runs. Child modules are
called from it. Keep one root module per independently deployed unit and one
state per root module and environment.

```text
infra/
  versions.tf        terraform block: required_version, required_providers, backend
  providers.tf       provider configuration (root module only)
  variables.tf       inputs with type, description, validation
  locals.tf          derived names and tags
  main.tf            resources and module calls
  outputs.tf         values consumed by pipelines or other stacks
  moved.tf           moved, import, and removed blocks
  environments/
    dev/backend.hcl          backend identifiers for dev state
    dev/terraform.tfvars     non-secret dev inputs
    prod/...
  modules/<name>/
    versions.tf variables.tf main.tf outputs.tf README.md
    tests/<name>.tftest.hcl
  tests/main.tftest.hcl
  .terraform.lock.hcl        committed provider lock file
```

The [blueprint index](blueprint.md) maps each file to a copyable template.

## Root versus child modules

- Configure providers only in the root module. A child module that contains a
  `provider` block cannot be used with `count`, `for_each`, or `depends_on`,
  and removing it from configuration strands its resources.
- Child modules declare `required_providers` with a minimum version and leave
  the upper bound to the root. Root modules choose a narrow, tested range.
- Pass provider aliases to modules explicitly through `providers = { ... }`
  when a module needs a second region or subscription.
- Keep modules small and purpose-shaped (a storage account with its secure
  defaults) rather than wrapping a single resource one-to-one.

## Version constraints

| Item | Root module | Child module |
| --- | --- | --- |
| Terraform CLI | `>= 1.10.0, < 2.0.0` | `>= <feature minimum>` |
| Provider | `~> 4.0` (pessimistic) | `>= 4.0.0, < 5.0.0` |
| Registry module | exact `version = "x.y.z"` | not applicable |
| Git module | `?ref=<full commit SHA>` | not applicable |

- `~> 4.0` allows 4.x but not 5.0; `~> 4.12.0` allows only 4.12.x.
- Commit `.terraform.lock.hcl`. It records the exact provider version and
  checksums. Generate checksums for every platform the team and CI use with
  `terraform providers lock -platform=linux_amd64 -platform=darwin_arm64
  -platform=windows_amd64` so a CI run never adds hashes silently.
- Upgrade providers deliberately (`terraform init -upgrade`) in a dedicated
  change, then read the provider changelog for resources in the plan.
- Never reference modules by branch (`?ref=main`) or unversioned registry
  source. A floating reference changes the plan without a code change.

## Naming and documentation

- Use `snake_case` for resource, variable, output, and local names. Name a
  module's single primary resource `this`.
- Give every variable and output a `description`; generate module READMEs with
  terraform-docs (see [static analysis](static-analysis.md)).
- Put cloud resource naming rules in `locals` once, and validate the inputs
  that feed them (see [variables and tests](variables-and-tests.md)).

## Review checklist

- [ ] `required_version` and `required_providers` present in every module.
- [ ] Provider blocks only in the root module.
- [ ] Lock file committed and covers CI and developer platforms.
- [ ] Registry modules pinned to exact versions; git sources pinned to SHAs.
- [ ] Each environment has its own backend configuration and state key.

## Sources

- <https://developer.hashicorp.com/terraform/language/modules/develop/structure>
- <https://developer.hashicorp.com/terraform/language/modules/develop/providers>
- <https://developer.hashicorp.com/terraform/language/expressions/version-constraints>
- <https://developer.hashicorp.com/terraform/language/files/dependency-lock>
- <https://developer.hashicorp.com/terraform/language/style>
