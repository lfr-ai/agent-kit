# IaC migrations

Every migration follows the same safety rule: one owner per resource at all
times. The old tool loses write access only after the new tool shows a
no-change preview for the same resources. Facts checked 2026-10.

## Common phases

1. **Freeze.** Stop applies from the old tool for the resources in scope;
   announce the window and disable scheduled runs.
2. **Back up.** Copy the state (or export the stack template and resource
   list) and enable versioning on the state store. Record checksums.
3. **Adopt.** Bring resources under the new tool with import blocks, a state
   conversion tool, or a native import operation. Never recreate a stateful
   resource to adopt it.
4. **Prove.** The new tool's preview must show no create, delete, or replace
   for adopted resources. Small in-place updates (tags, defaults) need a
   written decision.
5. **Cut over.** Remove the old tool's write permissions, archive its state,
   and switch CI. Keep the backup until the first successful apply.
6. **Roll back** if the preview cannot reach zero changes: restore the
   backup, return write access to the old owner, and record why.

## Terraform to OpenTofu

1. Confirm the Terraform version in use is one OpenTofu can read. OpenTofu
   reads Terraform 1.x state; Terraform may not read state written by
   OpenTofu, especially after OpenTofu-only features are used.
2. Back up state and commit all configuration.
3. Install OpenTofu, pin it in CI (`opentofu/setup-opentofu`), and run
   `tofu init` in a migration branch. Providers resolve from
   `registry.opentofu.org`; review the regenerated `.terraform.lock.hcl` and
   record new checksums for every platform CI uses
   (`tofu providers lock -platform=linux_amd64 -platform=darwin_arm64`).
4. Run `tofu plan` with the same variables and backend. Expect no changes.
5. Run `tofu apply` once (even with no changes) so state is written by
   OpenTofu, then make a small tag change to prove the full cycle.
6. For root modules connected by `terraform_remote_state`, migrate the
   consumers first and the producers last, so a configuration still on
   Terraform never reads state written by OpenTofu.

Caveats:

- Avoid enabling OpenTofu state encryption, `.tofu` files, or other
  OpenTofu-only features until rollback to Terraform is no longer needed.
  Encryption in particular makes state unreadable by Terraform.
- HCP Terraform features (remote runs, Sentinel, Stacks, private registry)
  need a replacement: a TACOS platform, self-hosted CI, or a private registry.
- Language features added to Terraform after the fork may not exist in
  OpenTofu, and the reverse. Run `tofu validate` and `tofu test` in CI before
  switching.
- Third-party CI actions, linters, and scanners must support the `tofu`
  binary; TFLint and Trivy read HCL regardless of CLI.

## Terraform and Bicep on Azure

Coexistence rule: a resource is owned by Terraform or by Bicep, never both.

- Divide by layer or by resource group: for example the platform team's Bicep
  deployment stacks own the landing zone, and workload Terraform reads its
  outputs with data sources.
- Bicep or ARM to Terraform: use Azure Export for Terraform (`aztfexport`) to
  generate HCL and state for a resource, resource group, or query result, or
  write `import` blocks and run `terraform plan -generate-config-out=generated.tf`.
  Treat generated code as a draft: replace literals with variables, remove
  read-only properties, and split it into modules. Delete the deployment stack
  with resources detached, not deleted, before Terraform takes over.
- Terraform to Bicep: remove resources from Terraform with
  `removed { from = ... lifecycle { destroy = false } }`, then deploy Bicep
  that declares the same resources and confirm what-if reports no change.
- `az bicep decompile` converts ARM JSON to Bicep; review the output for
  hard-coded values before use.

## Other import tools

- Terraform `import` blocks (1.5 and later; `for_each` from 1.7) are the
  reviewed path for any provider. `terraform query` with list resources (1.14
  and later) can discover existing objects and generate import configuration
  where providers support it.
- Google Cloud: `gcloud beta resource-config bulk-export
  --resource-format=terraform` generates Terraform for a project, folder, or
  organization through Config Connector.
- AWS: the CloudFormation IaC generator scans an account and Region and
  produces templates for CloudFormation import or CDK migration.
- Terraformer (formerly a broad multi-cloud exporter) is archived; do not
  choose it for new work.

## CloudFormation to CDK

- `cdk migrate` (preview feature) creates a CDK app from a deployed stack, a
  local template, or resources found by the IaC generator. Review the result
  and refactor into constructs.
- To keep an existing stack and evolve it gradually, wrap the template with
  the `cloudformation-include` module (`CfnInclude`) and replace resources one
  at a time.
- Keep logical IDs stable: a changed logical ID means a replacement. Compare
  `cdk diff` and the change set before deploying.

## Deployment Manager to Infrastructure Manager

Deployment Manager support ended on 2026-03-31 and the service is turned down
after 2027-06-30; migrate now.

1. Convert configurations and templates with DM Convert to Terraform. Some
   Deployment Manager concepts have no Terraform equivalent; list them and
   redesign.
2. Import the existing resources into Terraform state (import blocks or
   generated import commands) and run a preview until it reports no changes.
3. Deploy through Infrastructure Manager (or your own Terraform CI) with a
   preview first. Infrastructure Manager rolls forward by redeploying a prior
   configuration; there is no automatic rollback.
4. Abandon the Deployment Manager deployment without deleting its resources,
   then remove Deployment Manager permissions.

## Migration plan checklist

- [ ] Scope lists every resource, its current owner, and its new owner.
- [ ] State and templates are backed up with checksums; versioning is on.
- [ ] Adoption uses import or state conversion, never recreate-and-copy.
- [ ] The new tool's preview reports zero create, delete, or replace.
- [ ] The old tool's write access is removed on a recorded date.
- [ ] Rollback steps were rehearsed on a non-production boundary.

## Sources

- <https://opentofu.org/docs/intro/migration/migration-guide/>
- <https://opentofu.org/docs/intro/migration/multiple-configurations/>
- <https://opentofu.org/docs/language/state/encryption/>
- <https://developer.hashicorp.com/terraform/language/import>
- <https://developer.hashicorp.com/terraform/language/import/generating-configuration>
- <https://developer.hashicorp.com/terraform/language/resources/syntax#removing-resources>
- <https://learn.microsoft.com/en-us/azure/developer/terraform/azure-export-for-terraform/export-terraform-overview>
- <https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/decompile>
- <https://cloud.google.com/docs/terraform/resource-management/export>
- <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/generate-IaC.html>
- <https://docs.aws.amazon.com/cdk/v2/guide/migrate.html>
- <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.cloudformation_include-readme.html>
- <https://cloud.google.com/deployment-manager/docs/deprecations>
- <https://cloud.google.com/deployment-manager/docs/dm-convert>
- <https://github.com/GoogleCloudPlatform/terraformer>
