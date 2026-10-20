# What-if review and deployment stacks

## Deployment modes

- Incremental mode (the default) creates and updates resources in the
  template and leaves others in the resource group untouched.
- Complete mode deletes resources in the resource group that are not in the
  template. Treat any complete-mode deployment as destructive and require the
  what-if to show every `Delete` explicitly approved. Prefer deployment stacks
  for lifecycle-managed deletion.

## Running what-if

The operator runs what-if with the same template, parameter file, scope, and
identity class that will deploy:

```shell
az deployment group what-if \
  --resource-group <rg> \
  --parameters parameters/prod.bicepparam \
  --result-format FullResourcePayloads \
  --no-pretty-print --output json > whatif.json
```

- `FullResourcePayloads` returns full property deltas; `ResourceIdOnly` hides
  them and is unsuitable for review.
- What-if needs read access to the target scope and evaluates the template
  server-side, including `reference()` calls where possible.
- Use `az deployment sub what-if` or `mg what-if` for higher scopes.
- `az deployment group create --confirm-with-what-if` shows the preview and
  prompts before deploying in interactive sessions.

## Change types

| changeType | Meaning | Review action |
| --- | --- | --- |
| `Create` | Resource will be created | Check names, SKU, network exposure |
| `Modify` | Properties change; see `delta` | Read each property path |
| `NoChange` | Resource unchanged | None |
| `Delete` | Removed (complete mode or stacks) | Owner approval and recovery plan |
| `Recreate` | Deleted and created again | Owner approval; data and identity loss check |
| `Ignore` | Exists but not in the template, or beyond nesting limits | Confirm the resource is owned elsewhere |
| `Deploy` | Redeployed; property changes unknown (seen with `ResourceIdOnly`) | Re-run with `FullResourcePayloads` |
| `Unsupported` | What-if does not support this resource | Manual review; consider a test deployment |

The `delta` array lists `propertyChangeType` values `Create`, `Delete`,
`Modify`, `Array`, and `NoEffect`. `NoEffect` changes are read-only properties
that will be ignored; they are noise, not drift.

## Noise and false positives

What-if can report changes on properties the resource provider normalizes
(casing, defaulted values, reordered arrays). Do not ignore them blindly:
reproduce with a no-op template change, then record known-noise paths per
resource type so future reviews can focus on real changes.

## Reviewer contract

[review_whatif.py](../assets/review_whatif.py) accepts a top-level `changes`
array or a `properties.changes` envelope (not both), requires a successful
status, unique `resourceId` values, and a known `changeType`. It prints JSON
`summary` counts and `lists`; exits 2 for malformed input, 3 for deletes, and
4 for `Recreate`, `Deploy`, `Ignore`, or `Unsupported`. It never authorizes a
deployment.

## Deployment stacks

A deployment stack (`Microsoft.Resources/deploymentStacks`) manages the
resources from a template as a unit and tracks what it owns.

- `--action-on-unmanage` decides what happens to resources dropped from the
  template: `detachAll` (keep them, stop managing), `deleteResources`, or
  `deleteAll` (resources and resource groups). Default to `detachAll` and
  require an explicit change with what-if evidence to delete.
- `--deny-settings-mode` (`none`, `denyDelete`, `denyWriteAndDelete`) places
  deny assignments on managed resources so out-of-band changes fail. Use
  `--deny-settings-excluded-principals` for break-glass identities and
  `--deny-settings-apply-to-child-scopes` where children must be protected.
- Create stacks at a higher scope than the resources (for example
  subscription scope deploying to a resource group) so workload teams cannot
  modify the stack or its deny assignments.
- Managing deny settings requires the Azure Deployment Stack Owner role.

```shell
az stack group create \
  --name orders-prod \
  --resource-group <rg> \
  --parameters parameters/prod.bicepparam \
  --action-on-unmanage detachAll \
  --deny-settings-mode denyDelete
```

## Review checklist

- [ ] What-if used `FullResourcePayloads` at the correct scope.
- [ ] Every `Delete`, `Deploy`, `Ignore`, and `Unsupported` change is explained.
- [ ] `Modify` deltas on identity, network, encryption, and access settings
      are reviewed property by property.
- [ ] Complete mode and stack deletions have owner approval.
- [ ] Stack `action-on-unmanage` and deny settings match the intended
      lifecycle.

## Sources

- <https://learn.microsoft.com/azure/azure-resource-manager/templates/deploy-what-if>
- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-what-if>
- <https://learn.microsoft.com/azure/azure-resource-manager/templates/deployment-modes>
- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/deployment-stacks>
- <https://learn.microsoft.com/cli/azure/stack/group>
