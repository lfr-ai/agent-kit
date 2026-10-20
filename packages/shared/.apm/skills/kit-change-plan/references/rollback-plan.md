# Rollback plan

Decide how to undo each step **before** taking it. A rollback plan written after
something broke is improvisation under pressure.

## Rollback, roll forward, or neither

| Option | When it fits | Cost |
| --- | --- | --- |
| Revert the code change | stateless change; previous version still compatible with current data | fast, low risk |
| Turn off a toggle | change shipped behind a toggle | fastest; requires the toggle to exist and be tested in both states |
| Roll forward with a fix | fix is small and well understood; reverting would be riskier (for example after a data migration) | depends on the fix |
| Restore from backup | data was damaged | slow; loses changes since the backup |
| No rollback possible | irreversible step (data deleted, message sent, version published) | must be avoided or explicitly approved |

## Design for reversibility

- **Separate code from data changes.** Ship schema and data changes as
  expand/contract steps so each deploy can be reverted without touching data:
  add new structures, write both, backfill, switch reads, stop writing old, and
  only then remove old structures in a separate, final step.
- **Keep old and new compatible.** The previous release must run against the
  new schema until the contract step; the new release must tolerate old data.
- **Toggles for behavior.** Ship risky behavior dark and enable it separately;
  test both toggle states.
- **Idempotent operations.** Backfills, imports and retries can run twice
  without harm, so a partial run can be resumed instead of undone.
- **Backups and exports before destructive steps**, with a tested restore.
- **Published artifacts are immutable.** A bad release is replaced by a new
  version, never overwritten.

## Rollback plan per slice

For each slice record:

1. **Undo action**: the exact steps or commands (revert commit, toggle off,
   run down-migration, restore export).
2. **Point of no return**: the step after which undo is no longer possible, and
   what replaces it (roll forward, restore).
3. **Trigger**: the signal that starts a rollback (failing check, error rate,
   data mismatch, reviewer veto) and who decides.
4. **Verification**: how to confirm the system is back to the previous
   behavior.
5. **Data handling**: what happens to records written by the new version during
   its lifetime.

The [plan template](../assets/plan.md.template) and
[slice template](../assets/slice.md.template) have fields for these.

## Rehearse

- Run the undo action once in a disposable environment for any slice that
  changes data or deployment order.
- Time it; a rollback that takes longer than the acceptable outage is not a
  plan.
- Record the result in the plan's evidence section.

## Stop conditions

Stop and re-plan, without proceeding to the next slice, when:

- A rollback rehearsal fails or the point of no return is unclear.
- The undo action needs access or approval nobody has confirmed.
- New evidence shows old and new versions cannot run side by side.

## Sources

- [Martin Fowler: Parallel Change](https://martinfowler.com/bliki/ParallelChange.html)
- [Martin Fowler: Feature Toggles](https://martinfowler.com/articles/feature-toggles.html)
- [Google SRE book: release engineering](https://sre.google/sre-book/release-engineering/)
- [Azure Well-Architected: safe deployment practices](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/safe-deployments)
