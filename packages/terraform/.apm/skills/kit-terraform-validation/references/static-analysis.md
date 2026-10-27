# Static analysis pipeline

Run cheap, offline checks first and stop at the first failing stage. None of
these stages needs cloud credentials.

| Order | Command | Catches |
| --- | --- | --- |
| 1 | `terraform fmt -check -recursive -diff` | Formatting drift |
| 2 | `terraform init -backend=false` then `terraform validate` | Syntax, references, provider schema errors |
| 3 | `terraform test` (root and each module) | Broken contracts and validation rules |
| 4 | `tflint --init` then `tflint --recursive` | Deprecated syntax, invalid instance types, naming, unused declarations |
| 5 | `trivy config .` or `checkov -d .` | Insecure settings (public access, missing encryption, weak TLS) |
| 6 | `terraform-docs . --output-check` | Stale module documentation |

## TFLint

- Enable the bundled `terraform` ruleset with the `recommended` preset and a
  cloud ruleset (`azurerm`, `aws`, `google`) pinned to a version.
- `call_module_type = "local"` inspects local child modules; `"all"` also
  inspects downloaded registry modules.
- Silence a rule inline only with a reason:
  `# tflint-ignore: terraform_unused_declarations # kept for module consumers`.

## Trivy and Checkov

- Choose one configuration scanner, not both by default. The Trivy template
  selects only Terraform misconfiguration scanning; keep repository credential
  checks in the existing secret scanner. Hadolint and zizmor cover other targets
  and do not replace Terraform security analysis.
- Both scan HCL for misconfigurations; both can also scan a plan JSON, which
  resolves variables and module outputs that static HCL scanning cannot see.
- Fail on HIGH and CRITICAL; record accepted findings in an ignore file
  (`.trivyignore`, or `#checkov:skip=CKV_...:reason` comments) with an owner
  and expiry. Never lower the severity threshold to pass a build.
- Scan plan JSON only where the runner is trusted, because it contains
  sensitive values.

## terraform-docs

Generate module READMEs from source so inputs, outputs, and provider
requirements cannot drift from documentation. Use injection mode between
`BEGIN_TF_DOCS` and `END_TF_DOCS` markers and run with `--output-check` in CI.

## Pre-commit integration

Run stages 1, 2, 4, and 6 in pre-commit for fast feedback; keep tests and
security scans in CI where tool versions are pinned.

## Review checklist

- [ ] All six stages run in CI with pinned tool versions.
- [ ] Linter and scanner suppressions carry a reason, owner, and expiry.
- [ ] Module READMEs are generated, not hand-edited.

Templates: [.tflint.hcl](../assets/blueprint/.tflint.hcl.template),
[trivy.yaml](../assets/blueprint/trivy.yaml.template),
[.terraform-docs.yml](../assets/blueprint/.terraform-docs.yml.template),
[plan workflow](../assets/blueprint/github/terraform-plan.yml.template).

## Sources

- <https://developer.hashicorp.com/terraform/cli/commands/fmt>
- <https://developer.hashicorp.com/terraform/cli/commands/validate>
- <https://github.com/terraform-linters/tflint/blob/master/docs/user-guide/config.md>
- <https://trivy.dev/docs/latest/guide/coverage/iac/terraform/>
- <https://www.checkov.io/7.Scan%20Examples/Terraform%20Plan%20Scanning.html>
- <https://terraform-docs.io/user-guide/configuration/>
