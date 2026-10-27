# Deployment strategies

Verified as of 2026-10-27 against Microsoft Learn (Container Apps revisions,
traffic splitting, blue-green; App Service deployment slots), the Argo Rollouts
and Flagger documentation, and the Google SRE workbook chapter on canarying.
The Azure targets are covered in depth here; the equivalent primitives on AWS
(ECS deployment strategies, Lambda weighted aliases) and Google Cloud (Cloud
Run revisions and traffic splitting) are in `cloud-targets.md`.

## Choose by blast radius and reversibility

| Strategy | Exposure during rollout | Rollback | Needs | Fits |
| --- | --- | --- | --- | --- |
| Recreate | outage while old stops and new starts | redeploy previous | nothing | batch jobs, dev |
| Rolling | mixed versions, growing share | roll forward or redeploy previous; slow | readiness probes, version-compatible APIs and data | stateless services with good probes |
| Blue-green | none until switch, then 100% | switch back while old stays warm | double capacity during release, a router | services that need instant rollback |
| Canary | small share first (for example 10%, then 50%) | shift weight back | weighted routing, per-version metrics, abort thresholds | user-facing services with enough traffic to measure |
| Dark launch / feature flag | code deployed but inactive; enable per cohort | turn the flag off | flag service, flag hygiene | separating deploy from release |
| Shadow / mirror | copies of real requests, responses discarded | nothing to roll back | idempotent or side-effect-free paths | performance and correctness comparisons |

A canary is a partial and time-limited deployment plus an evaluation that
decides whether to continue (SRE workbook). Without the evaluation it is only a
slow rollout. Write the evaluation before the rollout: which signals, compared
against what, over which window, and what threshold aborts.

## Deploy is not release

Separate putting a version on servers (deploy) from exposing behavior to users
(release). Ship new behavior dark behind a flag, deploy it through the normal
pipeline, then release by flag to an internal cohort, a percentage, and
everyone. Every flag has an owner, a default that is safe when the flag
service is unreachable, and a removal date; stale flags are dead code with a
runtime switch.

## Azure Container Apps: revisions, weights, labels

- A revision is an immutable snapshot of the `properties.template` section
  (image, containers, scale rules, revision suffix). Changes under
  `properties.configuration` (secrets, ingress, traffic, labels, registries)
  apply to all revisions and do not create one; restart revisions to pick up
  new secret values.
- Single revision mode keeps the old revision serving until the new one is
  provisioned, scaled to the previous replica count, and passing startup and
  readiness probes; a failed update leaves traffic on the old revision.
- Multiple revision mode lets you split traffic by weight (weights sum to
  100) and activate or deactivate revisions. Inactive revisions cost nothing;
  up to 100 are kept and the oldest are purged beyond that.
- Labels give a revision a stable URL (`<app>---<label>.<environment
  domain>`) independent of weights; a label points at one revision at a time
  and moving it keeps the URL. Use a `candidate` label to test a revision at
  0% traffic, and `stable` / `previous` labels to make rollback targets
  explicit. Deployment labels as a revision mode are in preview.
- Revision names are `<app>--<suffix>`; set a deterministic suffix (run
  number plus digest prefix) so workflows can address the revision.
- Pin traffic by revision name before creating a new revision. A rule with
  `latestRevision: true` moves traffic to the newest revision as soon as it
  is ready, which turns a canary into a full release.

Canary sequence used by the delivery template:

1. Record the stable revision (highest weight).
2. Pin traffic to it by name, create the candidate from `image@digest`, and
   wait for `provisioningState` `Provisioned`.
3. Label it `candidate` and smoke test the label URL at 0% traffic.
4. For each weight (for example 10 then 50): set weights, bake, evaluate.
5. Promote to 100%, move `stable` to the candidate and `previous` to the old
   revision, keep the old revision active at 0% for instant rollback, and
   deactivate older revisions.
6. On any failure, set the stable revision to 100% and deactivate the
   candidate.

## Azure App Service: deployment slots and swap

- Slots require Standard, Premium, or Isolated plans; each slot is a live app
  with its own host name.
- Deploy to `staging`, verify there, then swap with `production` as the
  target. App Service applies the target slot's sticky settings to the source,
  restarts it, warms up every instance, and only then switches routing, so
  production stays online throughout. A failed restart or warm-up cancels the
  swap.
- Warm-up: `WEBSITE_SWAP_WARMUP_PING_PATH` (for example `/healthz`) and
  `WEBSITE_SWAP_WARMUP_PING_STATUSES` (for example `200`) make the swap wait
  for a real readiness answer; by default any HTTP response counts as warm.
  `applicationInitialization` in `web.config` serves the same purpose for
  Windows apps.
- Mark environment-specific app settings and connection strings as slot
  settings so they stay with the slot. Managed identities, custom domains,
  TLS settings, scale settings, IP restrictions, and virtual network
  integration are not swapped.
- Rollback is the same swap again: after a swap the staging slot holds the
  previous production content. Long-running work in recycled instances is
  abandoned, so handlers must tolerate interruption.
- Swap with preview (`--action preview`, then `swap` or `reset`) pauses after
  the configuration is applied, letting you validate the source slot with
  production settings. It is not available when site authentication is
  enabled on either slot.
- Traffic routing (`az webapp traffic-routing set --distribution
  staging=10`) sends a share of production traffic to a slot; a routed client
  is pinned for about an hour by the `x-ms-routing-name` cookie, which makes
  per-user experience consistent but slows rollback for pinned users.

## Kubernetes progressive delivery

A plain Deployment `RollingUpdate` offers little control of speed and traffic
and cannot analyze metrics or roll back automatically. When the consumer
runs Kubernetes:

- Argo Rollouts replaces the Deployment with a `Rollout` resource that
  supports canary and blue-green steps, weighted traffic through ingress
  controllers or service meshes, analysis against metric providers, and
  automated promotion or abort.
- Flagger (a Flux project) drives canary, A/B, and blue-green releases for
  existing Deployments through a service mesh or ingress (including Gateway
  API) and gates each step on metric checks.
- Both fit GitOps: the pipeline changes the desired image digest in Git and
  the controller performs the rollout (see `gitops.md`).

Edge routing configuration (Ingress, Gateway API routes, proxies) is owned by
`kit-edge-networking`.

## Database and other shared state

The new and old versions run at the same time during every strategy above
except recreate. Schema and data changes must therefore be compatible with
both versions: expand (add nullable columns, new tables), deploy code that
writes both shapes, backfill, switch reads, and only later contract (drop old
columns) in a separate release. The procedure, lock review, and rollback modes
belong to `kit-database-migrations`. Message and event schemas follow the same
rule: consumers accept both shapes before producers change.

## Health gates and automatic rollback

| Gate | Checks | Fails the rollout when |
| --- | --- | --- |
| Readiness | the instance can serve (dependencies reachable, warm caches) | the platform never reports the revision or slot ready |
| Smoke | a few critical requests against the candidate URL | any request fails |
| Synthetic journeys | scripted user flows against production after promotion | a journey fails |
| Canary analysis | error ratio, latency percentiles, and saturation of the candidate compared with stable over the bake window | the candidate is worse than stable by more than the threshold |
| SLO burn rate | multi-window burn-rate alerts on the service SLO | a fast-burn alert fires during or soon after the rollout |

Define SLIs, burn-rate windows, and alert routing with `kit-observability`;
the delivery pipeline consumes them as abort signals. A canary that receives
too little traffic cannot produce a statistically useful comparison; extend
the bake time or use synthetic load rather than trusting a quiet window.
Automatic rollback should be a traffic switch, never a rebuild.

## Sources

- <https://learn.microsoft.com/en-us/azure/container-apps/revisions>
- <https://learn.microsoft.com/en-us/azure/container-apps/traffic-splitting>
- <https://learn.microsoft.com/en-us/azure/container-apps/blue-green-deployment>
- <https://learn.microsoft.com/en-us/cli/azure/containerapp/revision/label>
- <https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots>
- <https://learn.microsoft.com/en-us/cli/azure/webapp/config/container>
- <https://argo-rollouts.readthedocs.io/en/stable/>
- <https://docs.flagger.app/>
- <https://sre.google/workbook/canarying-releases/>
