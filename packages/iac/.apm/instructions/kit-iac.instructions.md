---
description: Apply to cross-tool infrastructure-as-code review for Bicep and Terraform sources.
applyTo: "**/*.bicep,**/*.bicepparam,**/bicepconfig.json,**/*.tf,**/*.tfvars,**/*.tf.json,**/*.hcl"
---

- Validate the infrastructure actually present; do not add dormant tool stacks or a second IaC tool for the same resources.
- Give each resource one owning stack; other stacks reference it instead of redeclaring it.
- Parameterize per environment and keep differences in parameter or variable files, not copied templates.
- Pin tools, providers, modules, and images.
- Use least privilege, secret stores, private defaults, encryption in transit and at rest, and bounded cost through SKUs, scaling limits, and retention.
- Tag resources with owner, environment, and cost metadata according to repository policy.
- Separate static validation (format, lint, build, policy scan) from authenticated previews and approved deployment.
- Review destructive replacement, state ownership, network exposure, data retention, and rollback before approving a plan.
- Protect stateful resources with deletion locks or lifecycle guards where the platform supports them.
- Bring changes made outside code back under code by import or revert; never leave drift undocumented.
- Do not apply changes to external resources in an agent authoring session.
- Use the `kit-infra-review` skill for review procedures.
