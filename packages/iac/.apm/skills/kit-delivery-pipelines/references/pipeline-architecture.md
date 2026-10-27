# Pipeline architecture: build once, promote everywhere

Verified as of 2026-10-27 against the GitHub Actions, Docker, and DORA
documentation listed under Sources.

## CI and CD are different stages with different contracts

| Stage | Question it answers | Runs on | Produces | Never does |
| --- | --- | --- | --- | --- |
| Continuous integration | Is this change safe to merge and ship? | every pull request, merge queue entry, and trunk push | test results, one immutable artifact per trunk commit, provenance | deploy to a shared environment, hold cloud credentials |
| Continuous delivery | Can this exact artifact run in the next environment? | trunk artifacts only | deployment records, environment state, release evidence | build, compile, or resolve dependencies |
| Continuous deployment | Delivery with no human gate before production | same | same | skip the automated gates that replace the human |

Keep the stages in separate jobs (and usually separate workflows) so that the
integration stage never holds deployment credentials and the delivery stage
never runs untrusted pull request code. Workflow security review of that
boundary belongs to `kit-ci-review`.

## Trunk-based development is the input

Continuous delivery assumes small batches merged to one trunk at least daily:
three or fewer active branches, no code freezes, and no integration phases
(DORA trunk-based development capability). Long-lived branches turn every
release into a merge project and hide the integration risk the pipeline is
supposed to expose. Practical consequences:

- Unfinished work merges behind a feature flag or a branch by abstraction, not
  on a branch.
- The pipeline builds from trunk commits. Release branches exist only to patch
  an older supported version, and fixes land on trunk first.
- Review must be fast enough that people do not batch changes to avoid it.

## Build once, then promote the same immutable artifact

The artifact that reached production must be byte-for-byte the artifact that
passed every earlier gate. Rebuilding per environment silently re-resolves
base images, dependencies, and tool versions and invalidates every test you
ran on the previous build.

1. CI builds the artifact once from a trunk commit with locked dependencies.
2. CI pushes it to a registry and records its identity: the image digest
   (`sha256:...`) for containers, the file digest for packages.
3. CI attests provenance for that digest (`actions/attest`; the older
   `actions/attest-build-provenance` is now a wrapper around it). SBOM policy
   and verification depth belong to `kit-supply-chain`; the release-readiness
   decision belongs to `kit-release`.
4. CD receives the digest, verifies the attestation (`gh attestation verify
   oci://registry/name@sha256:... --repo owner/repo --signer-workflow
   owner/repo/.github/workflows/ci.yml`), and deploys `name@sha256:...` to each
   environment in order.
5. Environments differ only by configuration and secrets that the platform
   injects at runtime, never by a different artifact.

Tags are labels for people (`sha-<commit>`, `1.4.2`). Use them to look a
digest up once, then pass the digest. A tag can be moved; a digest cannot.
`check_delivery_workflow.py` flags tag references and build commands inside
deploy jobs.

### Artifacts versus registries

| Store | Use for | Avoid for |
| --- | --- | --- |
| Workflow artifacts (`actions/upload-artifact`) | handing files between jobs of one run, test reports, short-lived evidence | the deployable of record; retention is short and the store is per run |
| Container registry (GHCR, ACR) | images and OCI artifacts that CD promotes; attestations can be pushed next to the image | mutable `latest` tags as a deployment input |
| Package feed | libraries and installable packages | private service binaries that only CD consumes |

Keep the previous N production digests (at least the ones still referenced by
rollback targets) out of registry retention and cleanup policies.

## Reusable workflows and composite actions

| Mechanism | Unit | Can hold | Use for |
| --- | --- | --- | --- |
| Reusable workflow (`on: workflow_call`) | whole jobs | jobs, `environment`, job permissions, outputs | "deploy this digest to environment X", identical per environment |
| Composite action (`runs: using: composite`) | steps inside a job | steps, inputs, outputs | repeated step sequences such as a smoke probe |

Limits that shape the design: up to ten levels of nested workflows and up to
50 unique reusable workflows per caller tree; workflow-level `env` of the
caller does not reach the called workflow; the caller job may only set `name`,
`uses`, `with`, `secrets`, `strategy`, `needs`, `if`, `concurrency`,
`permissions`, and `cache-mode`; the called workflow can only narrow the
`GITHUB_TOKEN` permissions it receives. Because the caller job cannot carry
`environment`, pass the environment name as an input and set it on the called
job. For OIDC from reusable workflows, the token carries `job_workflow_ref`,
which a cloud trust policy can require.

## Monorepos: path filters and required checks

- Trigger per-component workflows with `paths` filters to save time, but do
  not make a path-filtered workflow a required check: a workflow skipped by a
  path or branch filter leaves its checks pending and blocks the merge, while a
  job skipped by `if:` reports success. A job skipped because a needed job
  failed may not block merging either. Require one gate job with `if:
  always()` that `needs` the component jobs and fails when any needed result
  is `failure` or `cancelled`.
- Add the `merge_group` trigger when a merge queue requires the checks.
- Give each deployable component its own image name, cache scope, deploy
  workflow, and concurrency group.
- Changes to shared libraries must trigger every dependent component; compute
  the affected set from the dependency graph rather than from directory names.

## Caching and its poisoning risk

| Cache | Key it on | Notes |
| --- | --- | --- |
| uv | `uv.lock` (`astral-sh/setup-uv` with `enable-cache` and `cache-dependency-glob`) | the action already skips caching on release, tag, `pull_request_target`, and `workflow_run` events in `auto` mode |
| npm, pnpm, Yarn | the lockfile (`actions/setup-node` `cache` plus `cache-dependency-path`) | cache the package manager store, not `node_modules` |
| Anything else | `actions/cache` with `hashFiles` of the lockfile in `key` | restore keys trade hit rate for staleness |
| Docker layers | BuildKit `type=gha` (scope per image) or `type=registry` (a dedicated cache image) | `mode=max` exports intermediate stages too |

A cache is code that a later job executes. Rules that limit poisoning:

- Caches are branch scoped: a run restores from its own branch, the base
  branch, and the default branch, never from sibling branches. Pull request
  caches are written to the merge ref and are not visible to the base branch.
- Only trusted triggers (`push`, `schedule`, `workflow_dispatch`, and a few
  others) can write the default-branch scope; `pull_request_target`,
  `issue_comment`, and `workflow_run` runs get read-only access. Use
  `actions/cache/restore` in such workflows and keep a trusted `push` build
  refreshing the cache. Set `cache-mode` to the least access a job needs.
- Never cache credentials, `.env` files, or build outputs that are deployed.
  The deployable comes from the registry by digest, never from a cache.
- Release builds may disable caches entirely; reproducibility beats speed for
  the artifact of record.

## Concurrency, timeouts, and bounds

- Pull request CI: cancel superseded runs with a group keyed on the pull
  request number and `cancel-in-progress` true only for `pull_request`
  events.
- Deployments: one group per service and environment, `cancel-in-progress:
  false`. Cancelling a deploy can leave traffic split or a slot half swapped.
  By default a newer pending run replaces an older pending one; set `queue:
  max` (up to 100 pending) when every queued deploy must run in order. `queue:
  max` cannot be combined with `cancel-in-progress: true`.
- Group names are case-insensitive and shared across workflows: a rollback
  workflow should use the same group as the deploy it can conflict with.
- Every job sets `timeout-minutes` (the default is 360 minutes). Deploy jobs
  get a timeout above the longest expected bake plus rollback.
- Bound matrices (`max-parallel`, explicit include lists) so a fan-out cannot
  exhaust runners or cloud quotas; never fan a deployment out across
  production regions without a wave order.

## Review checklist

- [ ] CI and CD are separate jobs; CD has no build step and no checkout of
      unreviewed code.
- [ ] One artifact per trunk commit, identified by digest, attested once.
- [ ] Every environment deploys `name@sha256:...` from the same digest.
- [ ] Required checks run on every pull request and cannot be skipped into
      success by path filters.
- [ ] Caches are keyed on lockfiles and never feed the deployable.
- [ ] Deploy concurrency queues; pull request concurrency cancels.
- [ ] `check_delivery_workflow.py` reports no findings or each is justified.

## Sources

- <https://dora.dev/capabilities/trunk-based-development/>
- <https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations>
- <https://github.com/actions/attest-build-provenance>
- <https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations>
- <https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching>
- <https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency>
- <https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks>
- <https://docs.docker.com/build/cache/backends/gha/>
- <https://github.com/astral-sh/setup-uv>
- <https://sre.google/workbook/canarying-releases/>
