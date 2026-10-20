# Rollback and recovery planning

A change is only ready when the team knows how to undo it. Recovery differs by
layer, and some changes cannot be undone at all; the review must say which.

## Classify reversibility

| Change | Reversible by | Not reversible when |
| --- | --- | --- |
| In-place update of configuration | Revert the commit, re-plan, re-apply | The old value depended on removed resources |
| Create | Revert and apply (deletes the new resource) | Other systems already depend on it |
| Replace or recreate | Restore from backup into a new resource | No backup, or identity-bound data (keys, certificates, managed identity principal IDs) |
| Delete | Restore from soft delete or backup | Soft delete disabled or retention expired |
| Role or network widening | Revert and apply | Data was already copied out; treat as an incident |
| State move, import, removal | Reverse block (`moved` back, `removed` with `destroy = false`) | Another state now manages the object |
| Image rollout | Redeploy the previous digest | Schema or data migrations ran forward only |
| Workflow change | Revert the workflow file | Secrets were exposed; rotate them |

## Layer-specific recovery

- **Terraform**: keep the remote backend's version history (blob versioning,
  bucket versioning) so a corrupted state can be restored. Rollback is a new
  plan from the previous commit, reviewed like any change; never hand-edit
  state.
- **Bicep and ARM**: redeploy the previous template version. Deployment
  history (`az deployment group list`) records what ran. Deployment stacks
  with `detachAll` keep removed resources instead of deleting them.
- **Data services**: confirm soft delete, point-in-time restore, or backups are
  enabled and tested before approving a replace or delete. Record the restore
  point time.
- **Containers**: deploy by digest so the previous digest is an exact
  rollback target. Keep migrations backward compatible for at least one
  release (expand, migrate, contract).
- **Workflows**: a reverted workflow does not revoke what a compromised run
  already did. Rotate credentials and review the audit log for the window.
- **Telemetry**: keep the previous collector configuration and alert rules
  deployable; a broken pipeline hides the effect of every other rollback.

## Before approval

1. Name the rollback owner and the decision signal (alert, error rate,
   failed health check) that triggers rollback.
2. Record the restore point (state version, backup time, previous digest,
   previous template commit).
3. For irreversible changes, require explicit acceptance of the
   irreversibility by the resource owner, and schedule them in a change
   window with the owner present.
4. Prefer progressive rollout (one environment, then one region or ring) so
   a rollback affects the smallest scope.

## Sources

- <https://learn.microsoft.com/azure/well-architected/operational-excellence/safe-deployments>
- <https://learn.microsoft.com/azure/azure-resource-manager/templates/rollback-on-error>
- <https://learn.microsoft.com/azure/storage/blobs/soft-delete-blob-overview>
- <https://developer.hashicorp.com/terraform/language/state/backends>
- <https://developer.hashicorp.com/terraform/language/modules/develop/refactoring>
