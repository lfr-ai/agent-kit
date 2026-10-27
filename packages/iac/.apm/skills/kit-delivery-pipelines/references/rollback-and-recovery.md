# Rollback and recovery for application releases

Verified as of 2026-10-27 against the Microsoft Learn, GitHub, and Google SRE
sources listed below. Infrastructure-change recovery (state, data-bearing
resources, restore points) is covered by `kit-infra-review`; this reference
covers getting a service back to a known-good release.

## Rollback or roll forward

Recovery time matters more than elegance. Decide quickly with explicit rules,
then write the decision into the incident timeline.

| Situation | Prefer | Why |
| --- | --- | --- |
| Impact began with the latest release and the previous release is still deployable | rollback by traffic switch | fastest, already proven in production |
| The release contained a contract migration or a one-way data transform | roll forward with a fix | the old version cannot read the new data |
| The cause is a configuration value or a flag | revert the configuration or turn the flag off | smaller change than an application rollback |
| The previous release has a known security defect that this release fixed | roll forward | rollback would reopen the vulnerability |
| The fix is trivial and the pipeline is faster than diagnosis | roll forward through the full pipeline | no side channels; every gate still runs |
| Cause unknown and impact ongoing | rollback first, investigate after | stop the bleeding |

A roll forward is still a normal pipeline run: build once, promote through
every environment, possibly with shorter bake times recorded on the gate
checklist. A hotfix that skips the pipeline creates an artifact nobody tested.

## Keep rollback targets alive

- Container Apps: keep the previous revision active at 0% traffic with the
  label `previous`; deactivate older ones. Container Apps keeps up to 100
  inactive revisions, which can be reactivated, and purges the oldest beyond
  that limit.
- App Service slots: after a swap the staging slot holds the previous
  production content; do not deploy to staging again until the new release has
  passed its bake period, or the instant rollback target is gone.
- Registry: exclude the last N production digests (at least those referenced
  by any active revision or slot) from retention policies. A digest that was
  garbage-collected cannot be redeployed.
- Kubernetes and GitOps: keep the previous desired state in Git history and
  the previous ReplicaSet according to the controller's revision history.

The rollback template supports both paths: switch to an existing revision, or
create a revision from an older attested digest when the revision was purged.
It refuses targets that do not run an image pinned by digest.

## Configuration and secrets

- Version configuration with the release when it changes behavior; apply
  environment-specific values through slot settings, revision-scoped
  environment variables, or a configuration service with history.
- In Container Apps, secrets and ingress are application scope: a rollback of
  the revision does not roll back a changed secret value or traffic rule.
  Record such changes separately in the release record.
- In App Service, slot settings stay with the slot during swaps; settings that
  are not sticky travel with the content and roll back with a swap back.
- Treat feature flags as configuration with an audit log; the runbook's first
  question is whether a flag changed.

## Data changes

Application rollback is only safe while the old version can still work with
the data the new version wrote. Expand-and-contract keeps that window open:
expand and backfill in release N, switch reads in N+1, contract in N+2 after
the rollback window for N+1 has passed. Record each migration's point of no
return; once a contract or destructive step runs, recovery is roll forward or
restore. The migration procedure belongs to `kit-database-migrations`.

## Runbooks

A runbook that has never run is a hypothesis. For each service:

- Keep the runbook next to the code (start from the runbook template) with the
  exact workflow names, inputs, dashboards, and contacts.
- Exercise the rollback in a lower environment on a schedule (for example once
  per quarter) and record the date in the runbook header.
- Measure time to restore during the exercise; it is the best predictor of
  failed deployment recovery time in production.

## Incident handoff

When a release causes impact:

1. The deploy owner or on-call engineer decides rollback or roll forward and
   records it.
2. Run the rollback workflow (or swap back) and confirm recovery with the
   smoke check and the SLO dashboard.
3. Mark the deployment as a change failure in the deployment export
   (`caused_incident: true`, `restored_at`) so delivery metrics stay honest.
4. Block re-promotion of the failed digest until a fix has merged.
5. Hand the timeline (deploy time, detection time, decision time, restore
   time, commands, approvers) to the incident review; add a test, a gate, or
   an alert so the same class of failure is caught earlier.

## Review checklist

- [ ] A rollback target exists for every environment and is healthy.
- [ ] The rollback path is a traffic switch or redeploy of an attested digest,
      never a rebuild.
- [ ] Registry retention preserves rollback digests.
- [ ] Each migration in the release states whether rollback is still possible.
- [ ] Configuration and flag changes are recorded with the release.
- [ ] The runbook was exercised recently and names current contacts.

## Sources

- <https://learn.microsoft.com/en-us/azure/container-apps/revisions>
- <https://learn.microsoft.com/en-us/azure/container-apps/blue-green-deployment>
- <https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots>
- <https://docs.github.com/en/rest/deployments/statuses>
- <https://sre.google/workbook/canarying-releases/>
- <https://dora.dev/guides/dora-metrics/>
