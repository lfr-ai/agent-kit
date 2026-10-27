---
name: kit-azure-validation
description: Use when writing Bicep, or reviewing Azure what-if output for destructive or scope changes.
license: MIT
---

# Validate Azure Bicep templates and what-if previews (read-only)

Review the authored Bicep, the parameter files, and the operator's what-if
output. Never run an authenticated deployment, stack update, or role change
during review. Start with the [review guide](references/guide.md).

## Procedure

1. Identify the entry template, `targetScope`, every scope modules deploy to,
   the parameter file per environment, the deployment mode (incremental,
   complete, or stack), and the deployment owner.
2. Confirm the template builds and lints with the repository
   `bicepconfig.json`: `az bicep build --file main.bicep`,
   `az bicep lint --file main.bicep`, and `az bicep build-params` for every
   `.bicepparam`. Record warnings that are accepted and why.
3. Review modules with [Bicep modules](references/bicep-modules.md): typed and
   described parameters, no secrets in outputs, `existing` for resources owned
   elsewhere, exact registry module versions (AVM or private), and stable API
   versions.
4. Review parameters, names, and tags with
   [parameters and naming](references/parameters-and-naming.md): no secret
   literals, `@secure()` values from Key Vault, deterministic names that obey
   per-type rules, and required tags.
5. Review identity and governance with
   [governance and identity](references/governance-identity.md): managed
   identities instead of keys, least-privilege role assignments named with
   `guid()`, OIDC with environment-bound subjects, and policy or locks on
   stateful production resources.
6. Accept only an operator-produced what-if JSON generated with
   `--result-format FullResourcePayloads` at the intended scope, with its
   command and checksum. Do not run `az deployment` yourself.
7. Run the [what-if reviewer](assets/review_whatif.py):
   `python assets/review_whatif.py --file whatif.json`. Exit 2 stops the
   review; request a regenerated preview.
8. For exit 3 or 4, read each `Delete`, `Recreate`, `Deploy`, `Ignore`, and
   `Unsupported` entry with [what-if and stacks](references/whatif-and-stacks.md)
   and record a per-resource decision. For stacks, confirm
   `action-on-unmanage` and deny settings match the intended lifecycle.
9. Read every `Modify` delta on identity, network, encryption, and access
   properties, and list every role assignment change with principal, role,
   and scope. Separate known provider noise from real drift.
10. When a consumer asks for a starting point, adapt the
    [blueprint](references/blueprint.md) and run its adoption check.
11. Produce the evidence bundle: commit, scopes, parameter file, what-if
    checksum, reviewer summary, per-resource decisions, accepted linter
    warnings, and the operator who may deploy. Hand the deployment to them.

## Acceptance gates

- [ ] Build, lint, and `build-params` succeed for every environment.
- [ ] No secrets in parameter files or outputs.
- [ ] What-if used `FullResourcePayloads` at the recorded scope.
- [ ] Reviewer exited 0, or every risky change has owner approval and a
      recovery plan.
- [ ] Access changes (roles, identities, network) are listed and approved.
- [ ] CI uses OIDC; deploy is gated by a protected environment.
- [ ] Deployment is handed to the named operator with the evidence bundle.

## Out of scope

A what-if review inspects intended changes. It does not reconcile drift,
repair live resources, or authorize deployment.
