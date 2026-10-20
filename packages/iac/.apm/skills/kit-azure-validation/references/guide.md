# Azure review guide: gates, contracts, and recovery

Use this guide to pick a reference and interpret the what-if reviewer.

## Reference map

| Concern | Reference |
| --- | --- |
| Modules, scopes, AVM, API versions | [Bicep modules](bicep-modules.md) |
| `.bicepparam`, secure parameters, naming, tags | [Parameters and naming](parameters-and-naming.md) |
| What-if output, change types, deployment stacks | [What-if and stacks](whatif-and-stacks.md) |
| Managed identity, RBAC, OIDC, policy, locks | [Governance and identity](governance-identity.md) |
| Copyable starting configuration | [Blueprint index](blueprint.md) |

## Quality gates

- Template and every parameter file build and lint without errors.
- What-if JSON was produced by the operator with `FullResourcePayloads`,
  at the intended scope, and recorded with its command and checksum.
- No `Delete` or `Recreate`, or each has recorded owner approval and a
  recovery plan; `Deploy`, `Ignore`, and `Unsupported` are explained.
- Role assignments, identities, network rules, and encryption changes are
  listed individually even when they are `Create` or `Modify`.
- Secrets reach the deployment only through `@secure()` parameters backed by
  Key Vault or pipeline secrets; outputs contain no secrets.
- CI authenticates with OIDC; deploy runs behind a protected environment.

## Failure modes

- What-if ran against the wrong subscription or resource group.
- Complete mode or a stack with `deleteResources` removed resources owned by
  another team.
- An API version upgrade changed a default and triggered recreation.
- A name built from `utcNow()` or `newGuid()` recreated a resource on every
  deployment.
- A role assignment granted `Contributor` at subscription scope to a workload.

## Negative cases the reviewer must reject

- Missing `changes` array, or both `changes` and `properties.changes`.
- `status` other than `Succeeded`, or a non-null `error`.
- Unknown or missing `changeType`, duplicate `resourceId`, duplicate JSON keys.
- A `delta` without a `changeType` (never inferred as `Modify`).

## What-if reviewer contract

[review_whatif.py](../assets/review_whatif.py) is a read-only stdlib reviewer.

- Input: an explicit `changes` array or a `properties.changes` envelope.
- Output: JSON `summary` counts and per-kind `lists`.
- Exit codes: 0 no risky change, 2 malformed or unsupported input,
  3 deletion, 4 recreation or unresolved (`Deploy`, `Ignore`,
  `Unsupported`) changes. No approval flags, authentication, or network use.
- `--self-test` runs built-in regressions.

```shell
python assets/review_whatif.py --file whatif.json
```

Exit 0 is not a deployment approval or a complete safety verdict; property
deltas, scope, identity, and RBAC still need human review.

## Recovery

1. Ask the operator to reproduce what-if with the documented command, scope,
   and parameter file, and to provide the raw JSON.
2. If the JSON is malformed, rerun in an approved environment; never edit it.
3. For `Delete` or `Recreate`, require owner approval and a rollback or data
   recovery plan; prefer a stack with `detachAll` over deletion.
4. If scope mismatch is suspected, regenerate against the correct scope and
   compare resource IDs.

## Prerequisites

- The authored Bicep, parameter files, and `bicepconfig.json`.
- The operator-produced what-if JSON and the intended deployment scope.
- Knowledge of policy assignments that apply to the target scope.

## Sources

- <https://learn.microsoft.com/azure/azure-resource-manager/templates/deploy-what-if>
- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/linter>
