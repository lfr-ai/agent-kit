# Cloud targets: identity, registries, and progressive delivery per cloud

Verified as of 2026-10-27 against the GitHub, Microsoft, AWS, and Google Cloud
documentation listed under Sources. Action versions in the templates were the
latest major releases on that date (`azure/login` v3,
`aws-actions/configure-aws-credentials` v6, `google-github-actions/auth` v3,
`google-github-actions/setup-gcloud` v3, `aws-actions/amazon-ecr-login` v2);
pin each to a reviewed full commit SHA.

The pipeline shape does not change between clouds: CI builds and attests one
digest, CD verifies it, deploys `name@sha256:...` to each environment through
an environment-scoped OIDC identity, shifts traffic in steps, smoke checks,
and rolls back by traffic switch. Only the identity setup, registry naming,
and the traffic-shifting primitive differ.

## OIDC federation per cloud

GitHub issues a short-lived OIDC token to jobs with `id-token: write`. The
`sub` claim of a job that names an environment is
`repo:<owner>/<repo>:environment:<name>`; repositories created after
2026-07-15 (or renamed or transferred after it, or opted in) emit
`repo:<owner>@<owner-id>/<repo>@<repo-id>:environment:<name>`. Every cloud
trust below must pin that subject (or an equivalent attribute) per
environment; never trust the whole issuer.

| Cloud | Trust object | Pin | Workflow step |
| --- | --- | --- | --- |
| Azure | federated identity credential on an Entra application or user-assigned managed identity (at most 20 per identity) | issuer `https://token.actions.githubusercontent.com`, exact `subject`, audience `api://AzureADTokenExchange`; no wildcards | `azure/login` with `client-id`, `tenant-id`, `subscription-id` |
| AWS | IAM OIDC identity provider for `token.actions.githubusercontent.com` plus an IAM role whose trust policy allows `sts:AssumeRoleWithWebIdentity` | `StringEquals` on `token.actions.githubusercontent.com:aud` = `sts.amazonaws.com` and on `token.actions.githubusercontent.com:sub` = the environment subject; IAM recommends always evaluating `sub` | `aws-actions/configure-aws-credentials` with `role-to-assume` and `aws-region` (`aws-region` is always required) |
| Google Cloud | Workload Identity Pool and an OIDC provider with an attribute mapping (`google.subject=assertion.sub` plus `attribute.repository`, `attribute.repository_owner`, and others you need) | an attribute condition that always restricts admission (for example `assertion.repository_owner == '<org>'`), then IAM bindings on a `principalSet` or a service account restricted to the environment subject or repository | `google-github-actions/auth` with `workload_identity_provider` (full `projects/<number>/locations/global/workloadIdentityPools/<pool>/providers/<provider>` name), optional `service_account`, and `project_id` |

Cloud-specific notes:

- AWS: GitHub notes that custom OIDC claims are not supported by AWS, so
  restrict on `sub` and `aud`. Prefer `StringEquals` with the full
  environment subject; use `StringLike` wildcards only for non-production
  read roles. Give each environment its own role, and a separate read-only
  role (trusting the trunk ref subject) for registry lookups outside
  environment jobs.
- Google Cloud: direct Workload Identity Federation (no service account)
  gives the pool permissions directly; the resulting token lives at most
  10 minutes, and the GitHub OIDC token itself expires after about 5 minutes.
  For deploy jobs with canary bake times, impersonate a deploy service
  account (`service_account` input, `roles/iam.workloadIdentityUser` granted
  to the environment principal) so access tokens last up to an hour. Run
  `actions/checkout` before `auth` when steps use the generated credentials
  file, and ignore `gha-creds-*.json` in build contexts. Pool and provider
  changes can take about 5 minutes to propagate.
- Azure: see `environments-and-approvals.md` for the full setup.

The delivery checker's `oidc-permission` rule recognizes all three login
actions and reports a deploy job that uses one without `id-token: write`.

## Registries and promotion by digest

| Registry | Image reference by digest | Pull identity for the runtime | Hardening |
| --- | --- | --- | --- |
| GitHub Container Registry | `ghcr.io/<owner>/<image>@sha256:...` | registry credential on the platform or a public image | attestations can be pushed next to the image |
| Azure Container Registry | `<registry>.azurecr.io/<image>@sha256:...` | managed identity with `AcrPull` | lock released images; retention excludes rollback digests |
| Amazon ECR | `<account>.dkr.ecr.<region>.amazonaws.com/<image>@sha256:...` | ECS task execution role | turn on tag immutability (all tags; `ImageTagAlreadyExistsException` on overwrite) with exclusions only where needed |
| Google Artifact Registry | `<location>-docker.pkg.dev/<project>/<repository>/<image>@sha256:...` | the Cloud Run service identity with Artifact Registry reader | cleanup policies keep rollback digests |

Rules that hold everywhere:

- CI pushes to the registry the runtime pulls from (or replicates by digest);
  copying an image between registries keeps the digest only when the
  manifest is copied unchanged, so verify the digest after any copy.
- CD resolves a lookup tag (for example `sha-<commit>`) at most once, then
  passes the digest; `gh attestation verify oci://<image>@sha256:...` needs
  registry credentials on the runner (`docker login`, `az acr login`,
  `aws-actions/amazon-ecr-login`, or `gcloud auth configure-docker`).
- Amazon ECS resolves task-definition tags to digests when a deployment
  starts so all tasks of a service run the same image; that does not make a
  tag a release identity. Register task definitions with the digest.

## Progressive delivery primitives per target

| Target | Primitive | Traffic control | Rollback | Template |
| --- | --- | --- | --- | --- |
| Azure Container Apps | revisions in multiple revision mode, labels (`<app>---<label>` URL) | revision weights summing to 100 | weight back to the previous revision kept active at 0% | `cd-container-apps.yml.template` |
| Azure App Service | staging slot plus swap with warm-up (`WEBSITE_SWAP_WARMUP_PING_PATH`) | optional percentage routing to a slot (`az webapp traffic-routing set`) | swap again | `cd-app-service-slots.yml.template` |
| Amazon ECS | ECS deployment controller with deployment strategies `ROLLING`, `BLUE_GREEN`, `CANARY` (one canary percentage, then the rest after a bake time), and `LINEAR` (equal steps with bake times between) | the service shifts load balancer, Service Connect, or VPC Lattice traffic; lifecycle hooks (Lambda or pause) run at stages such as `POST_TEST_TRAFFIC_SHIFT` and `PRODUCTION_TRAFFIC_SHIFT` | automatic on deployment alarms or circuit breaker where configured; `StopServiceDeployment` with `ROLLBACK`; the blue revision stays up during the bake time | `cd-aws-ecs.yml.template` |
| Amazon ECS (older setups) | `CODE_DEPLOY` deployment controller with CodeDeploy blue/green and an AppSpec | CodeDeploy traffic-shifting configurations | CodeDeploy rollback | adapt; not templated |
| AWS Lambda | published versions behind a weighted alias (at most two versions, `routing-config AdditionalVersionWeights`) | weights per alias; probabilistic, so low traffic varies | point the alias back at the previous version | CodeDeploy or SAM gradual deployments for automation |
| Google Cloud Run | revisions; `gcloud run deploy --no-traffic --tag <tag>` gives a tag URL (`https://<tag>---<service>-<hash>.a.run.app`) | `gcloud run services update-traffic --to-revisions <rev>=<percent>` or `--to-tags` | `update-traffic --to-revisions <previous>=100` | `cd-gcp-cloud-run.yml.template` |
| Kubernetes | Argo Rollouts or Flagger (see `gitops.md`) | ingress, Gateway API, or service mesh weights with metric analysis | controller abort plus a Git revert | adapt; not templated |

Target-specific cautions:

- ECS: the deployment strategy, canary percentage, bake time, load balancer
  test listener, lifecycle hooks, and alarm rollback live in the service
  definition (infrastructure code), not in the workflow. The workflow
  registers a task definition revision with the digest, updates the service,
  follows the service deployment status (`SUCCESSFUL`,
  `ROLLBACK_SUCCESSFUL`, `ROLLBACK_FAILED`, `STOPPED`), and stops it with
  rollback when its own checks fail. Blue/green and canary double capacity
  during the deployment; Network Load Balancers add about 10 minutes to the
  traffic-shift stages.
- Lambda: both versions behind an alias need the same execution role and
  dead-letter configuration, and the alias cannot point at `$LATEST`.
- Cloud Run: once traffic is split or pinned, later deployments keep that
  pattern until all traffic is sent to the latest revision again; that is
  what keeps a `--no-traffic` candidate at 0%. Tagged revisions can keep
  instances warm and incur cost; remove the candidate tag after promotion.
  Traffic changes are not instantaneous; in-flight requests finish on either
  revision.
- App Service and Cloud Run percentage routing are sticky or approximate per
  client; keep canary analysis on per-revision metrics, not on request
  counts alone.

## Choosing the target-specific template

Start from the cloud template, keep the shared skeleton (resolve and verify,
per-environment jobs with OIDC, smoke before and after traffic, rollback on
failure), and keep the infrastructure that defines services, identities, and
traffic policies in reviewed infrastructure code (`kit-terraform-validation`
or `kit-azure-validation`). Run `check_delivery_workflow.py` on the result.

## Sources

- <https://docs.github.com/en/actions/reference/security/oidc>
- <https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure>
- <https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws>
- <https://github.com/aws-actions/configure-aws-credentials>
- <https://github.com/google-github-actions/auth>
- <https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust>
- <https://learn.microsoft.com/en-us/azure/container-apps/traffic-splitting>
- <https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots>
- <https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-blue-green.html>
- <https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-ecs.html>
- <https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-alarm-failure.html>
- <https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentConfiguration.html>
- <https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CanaryConfiguration.html>
- <https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_ServiceDeployment.html>
- <https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_StopServiceDeployment.html>
- <https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-tag-mutability.html>
- <https://docs.aws.amazon.com/lambda/latest/dg/configuring-alias-routing.html>
- <https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration>
- <https://cloud.google.com/artifact-registry/docs/docker/manage-images>
- <https://argo-rollouts.readthedocs.io/en/stable/>
- <https://docs.flagger.app/>
