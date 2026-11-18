# Delivery changelog

Notable changes to the delivery package (`packages/delivery`) and the Copier
starter that consumes it, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Releases are tagged
`delivery-vX.Y.Z`; consumers pin the tagged commit's full SHA. See
[versions and upgrades](docs/consuming.md#versions-and-upgrades).

## Unreleased

### Added

- Stage-specific API `.env.dev.example`, `.env.test.example`,
  `.env.staging.example` and `.env.prod.example` alongside the local example.
  One shared template owns their settings; select one explicitly and keep real
  values out of Git. Remote TLS and keyless Azure modes remain explicit.
- Generated GitHub Dependabot configuration for actions, Docker and uv, plus
  regression checks for release digest attestations and plan-artifact retention.

- **Starter `registry` answer:** `acr` (default with cloud IaC) adds a
  per-environment Azure Container Registry from the `container-registry` module,
  OIDC push from CI, digest-pinned images and AcrPull through the user-assigned
  runtime identity. `ghcr` keeps the public GHCR path for dev or evaluation only.
- **Registry bootstrap:** a first deployment of an environment can create the
  registry and shared infrastructure without the app, on GitHub
  (`registry-bootstrap`) and Azure DevOps (`registryBootstrap`).
- **Starter `ci` answer:** `github` (default) or `azure-devops`. Azure DevOps emits
  `.azuredevops/pipelines/` callers (`ci.yml`, plus `iac.yml` and `deploy.yml`
  with cloud IaC) that extend the pinned `python-ci`,
  `bicep-check`/`terraform-check` and `azure-deploy`
  templates (with `deployBranch: refs/heads/main`), plus a manual ACR image
  pipeline. Only the selected system's files are generated.
- Release-tag convention, `copier update --vcs-ref` upgrade path and a migration
  guide for existing GitHub and Azure DevOps projects in
  [consuming](docs/consuming.md).

### Changed

- Alert destinations are email or a caller-owned action group (Teams/email);
  the starter's redundant transport selector is removed. Explicit unmonitored
  operation is dev/test-only; staging and prod require a destination.
- Console problem records retain bounded failure attribution. Subscription
  Activity Log export remains separately owned, once per subscription.

- **Staging is production-like** in starter infrastructure: internal Container
  Apps environment, disabled public access, zone redundancy, two or more
  replicas and deletion locks, as in prod. Cost choices such as the registry SKU
  stay explicit per environment, and staging now always needs a network CIDR.
- The starter's GitHub directory is generated only for `ci=github`.

### Removed

- Legacy inline Teams webhook inputs and the speculative per-app Resource
  Health rule. Existing destinations need an explicit reviewed ownership
  migration and delivery test; no cloud resources are destroyed by this change.

- **`front-door` module** (`infra/front-door`, Bicep and Terraform) and its
  integration test. Nothing consumed it: no starter, workflow, Azure DevOps
  template, bootstrap or other module referenced it. Git history restores it.
  Projects pinned to an older `delivery-vX.Y.Z` tag are unaffected, but must
  review before upgrading. Staging and production stay private; for public
  exposure add an operator-owned edge WAF or gateway outside this kit (see the
  Container Apps README, "Public exposure"). Removal never destroys deployed
  Front Door resources; delete those only through an explicit, reviewed
  operator action.

### Upgrade notes

- `copier update` gives existing API projects with IaC the new default
  `registry=acr`. Pass `--data registry=ghcr` to keep GHCR, or plan the registry
  bootstrap deployment before the first ACR deploy of each environment.
- Staging deployments after the upgrade move to an internal environment and add
  locks; an existing public staging environment can need replacement. Review the
  preview before applying.
- The pinned kit commit must contain the `container-registry` module and, for
  Azure DevOps, the `deployBranch` parameter of `extends/azure-deploy.yml`.
