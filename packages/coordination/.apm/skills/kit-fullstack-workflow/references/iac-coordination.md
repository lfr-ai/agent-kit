# Infrastructure coordination

Infrastructure as code (IaC) changes are part of the feature, not a separate
afterthought. They usually have the longest lead time (reviews, approvals,
provisioning) and the hardest rollbacks, so plan them first and land them
before the code that needs them.

## What to inventory

| Category | Examples | Lands before |
| --- | --- | --- |
| Compute and hosting | New function, container app, queue worker, static site route | Backend or frontend deployment that uses it |
| Data | Database, container, bucket, index, retention policy | Data expand step |
| Configuration | Application settings, feature switches defaulting off | Code that reads them |
| Secrets | Secret store entries and references, never values in code | Code that reads them |
| Identity and access | Managed identity, role assignments, least-privilege scopes | First call that needs the permission |
| Network | Private endpoints, firewall rules, CORS origins, DNS | First cross-network call |
| Observability | Log queries, dashboards, alerts for the new journey | Enablement of the feature switch |

## Procedure

1. List every item above that the journey needs, per environment, with the
   owner of the IaC repository or module.
2. Write the change in the existing IaC modules; reuse parameters for
   environment differences instead of copying definitions.
3. Run the tool's preview (plan or what-if) for each environment and attach
   the output to the review. Read it for deletions and replacements; a
   replacement of a stateful resource is a data-loss risk.
4. Apply through the approved pipeline, in environment order, and record the
   applied revision.
5. Verify from the consuming side: the application can read the setting,
   reach the endpoint and use the permission, using the same identity it will
   use in production.
6. Only then merge or enable code that depends on it.

## Configuration contract

Treat configuration keys like an API:

- Name, type, default and allowed values documented next to the code that
  reads them.
- Required keys fail fast at startup with a clear message naming the key,
  never the value.
- Removing or renaming a key follows expand and contract: add the new key,
  read both, remove the old key after every environment is updated.
- Frontend runtime configuration (API base URL, feature switches) comes from
  the hosting environment or a configuration endpoint, not from values baked
  into a build per environment, unless the project's convention says so.

## Secrets

- Secret values live only in the secret store; IaC and code hold references.
- Rotations are tested before they are needed: the application must pick up a
  new version without redeploying, or the rotation runbook says how.
- Previews, logs and contract examples are checked for accidental values.

## Rollback

- Additive resources can stay in place when code rolls back; remove them
  later as a cleanup.
- Permission grants are rolled back after the code that uses them.
- Destructive changes (deleting data stores, narrowing network rules) only in
  the contract phase, with a recorded backup or a reason none is needed.

## Sources

- [Terraform plan command](https://developer.hashicorp.com/terraform/cli/commands/plan)
- [Bicep what-if deployment preview](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if)
- [Twelve-Factor App: Config](https://12factor.net/config)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
