---
description: Apply to Terraform configuration, variables, and module declarations.
applyTo: "**/*.tf,**/*.tfvars,**/*.tfvars.json"
---

- Preserve backend and state ownership; never move, import, or mutate state implicitly.
- Use a remote backend with locking and encryption; never commit state files, plan files, or the `.terraform/` directory.
- Commit `.terraform.lock.hcl` and constrain `required_version`, providers, and modules using the repository's policy.
- Pin module sources to released versions or immutable refs, never floating branches.
- Type every variable, add `validation` blocks for ranges and formats, and mark secrets `sensitive = true` without committing values.
- Mark sensitive outputs, and avoid exposing secrets through outputs at all where possible.
- Prefer `for_each` with stable keys over `count` for collections so reordering does not recreate resources.
- Use `moved` blocks for refactors instead of manual state edits.
- Review replacement and destroy actions, `lifecycle` settings such as `prevent_destroy` and `ignore_changes`, and imported resources.
- Keep reusable modules small with explicit inputs and outputs, and no provider configuration inside them.
- Run format, validate, and the configured linters before an approved plan.
- Keep plans and state files out of source control and shared logs.
- Do not apply infrastructure from an authoring session.
- Use the `kit-terraform-validation` skill for validation steps.
