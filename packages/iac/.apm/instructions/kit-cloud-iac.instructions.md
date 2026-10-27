---
description: Apply to AWS CloudFormation, SAM, CDK, and Pulumi project and template files.
applyTo: "**/template.yaml,**/template.yml,**/samconfig.toml,**/cdk.json,**/Pulumi.yaml,**/Pulumi.*.yaml,**/*.cfn.yaml,**/*.cfn.json"
---

- Keep each resource owned by one stack and one tool; reference shared resources through exports, parameters, or stack outputs instead of redeclaring them.
- Preview every change (change set, `cdk diff`, `sam deploy --no-execute-changeset`, `pulumi preview`) and review replacements and deletions before deploying.
- Keep CDK construct IDs and CloudFormation logical IDs stable; a renamed ID replaces the resource.
- Set `DeletionPolicy` and `UpdateReplacePolicy` to `Retain` or `Snapshot` on stateful resources, and enable stack termination protection for production.
- Pin the CDK, SAM CLI, Pulumi CLI, and provider or package versions in lock files.
- Never commit secrets in templates, `samconfig.toml`, or Pulumi stack files; use Secrets Manager, SSM Parameter Store dynamic references, or Pulumi encrypted config.
- Run cfn-lint, CloudFormation Guard, or cdk-nag offline before any authenticated preview.
- Deploy with short-lived federated credentials from CI, never long-lived access keys.
- Do not deploy or change cloud resources from an authoring session.
- Use the IaC selection procedure in the `kit-infra-review` skill for tool choice, migration, and policy placement.
