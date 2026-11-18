# Azure deployment

The delivery package provides one deployment path for each platform. It deploys a caller-owned
Bicep template or Terraform root to one environment at a time. Each run previews the change
(Bicep what-if or a saved Terraform plan), waits for the environment's approvals, and then
applies exactly that preview. Azure access uses OpenID Connect (OIDC) workload identity
federation only: there are no client secrets, and no secret values appear in inputs, logs or
catalog entries. Strictness increases from dev to test to prod through each environment's
protection rules, not through extra inputs.

| Platform | Source | Unit |
| --- | --- | --- |
| GitHub | `.github/workflows/delivery-azure-deploy.yml` (repository root) | One `workflow_call` per environment; callers chain jobs |
| Azure Pipelines | [extends/azure-deploy.yml](../azure-devops/extends/azure-deploy.yml) | A preview stage and a deploy stage per listed environment |

## Caller repository layout

Both platforms read IaC from the caller's checkout:

- **Bicep**: `<working-directory>/main.bicep` is deployed to an existing resource group.
- **Terraform**: `<working-directory>` is a root module with an empty `backend "azurerm" {}`
  block and a committed `.terraform.lock.hcl`.
- **Parameters**: `<working-directory>/<environment>.bicepparam` or
  `<environment>.tfvars` unless overridden. JSON parameter files and `.tfvars.json` also work.

Callers keep their parameters in their own repository. A `.bicepparam` file may declare
`using './main.bicep'` or `using none`. The [fixture](../fixtures/bicep/deploy.bicepparam) is
compiled by the native tests. `.bicepparam` files are compiled once, in the preview, to
`params.json`. Deploy reuses that file, so values computed at compile time cannot drift between
preview and deploy. Keep secrets out of parameter files; see
[preview artifacts and secrets](#preview-artifacts-and-secrets).

The optional `image` (`registry/repository@sha256:<64 hex>`) is passed as `containerImage`
(Bicep) or `container_image` (Terraform). The template must declare that parameter. Promote one
digest unchanged through every environment.

### How the workflow gets its sources

All logic is inline in the pinned workflow or template, so the run never reads toolkit files.
This is why there is no `kit-ref` input. The caller's `uses: …@<sha>` or repository-resource
pin is the only revision. Delivery modules reach a deployment through the caller's template in
one of two ways:

- vendored into the caller repository by the starter; or
- for Terraform, referenced by a module source pinned to a full commit, for example
  `git::https://github.com/lfr-ai/agent-kit.git//packages/delivery/infra/container-apps/terraform?ref=<40-hex>`.

If a later version must read toolkit files, check them out with
[`job.workflow_repository` and `job.workflow_sha`](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts).
These contexts are available on GitHub.com but not on GitHub Enterprise Server. Prefer them to
a hand-maintained ref input.

## GitHub

### Calling the workflow

Replace the placeholder with the reviewed toolkit commit. Each job grants exactly what the
called jobs need: `actions: read` lets preflight read the environment's protection rules, and
`id-token: write` lets the plan and deploy jobs request the OIDC token.

```yaml
name: Deploy
on:
  push:
    branches: [main]
permissions: {}
jobs:
  dev:
    uses: lfr-ai/agent-kit/.github/workflows/delivery-azure-deploy.yml@<reviewed-full-sha>
    permissions: { contents: read, actions: read, id-token: write }
    with:
      environment: dev
      resource-group: rg-app-dev
  test:
    needs: dev
    uses: lfr-ai/agent-kit/.github/workflows/delivery-azure-deploy.yml@<reviewed-full-sha>
    permissions: { contents: read, actions: read, id-token: write }
    with:
      environment: test
      resource-group: rg-app-test
  prod:
    needs: test
    uses: lfr-ai/agent-kit/.github/workflows/delivery-azure-deploy.yml@<reviewed-full-sha>
    permissions: { contents: read, actions: read, id-token: write }
    with:
      environment: prod
      resource-group: rg-app-prod
```

For Terraform, use `iac: terraform` and omit `resource-group`. To promote a built image, add
`image: ${{ needs.build.outputs.image }}` to every job.

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `environment` | string | required | GitHub environment name: 1-32 lowercase letters, digits, `-` or `_` |
| `iac` | string | `bicep` | `bicep` or `terraform` |
| `working-directory` | string | `infra` | Repository-relative IaC directory |
| `parameters` | string | `<environment>.bicepparam` / `.tfvars` | Relative to `working-directory` |
| `resource-group` | string | none | Existing target group; required for Bicep, rejected for Terraform |
| `image` | string | none | Optional digest-pinned image |
| `health-url` | string | none | Optional HTTPS URL that must answer `2xx` after deployment |
| `protected` | boolean | `false` | Require reviewers; `prod` and `production` are always protected |
| `bicep-version` | string | `0.48.1` | Exact Bicep CLI version |
| `terraform-version` | string | `1.16.7` | Exact Terraform version |
| `runs-on` | string | `ubuntu-24.04` | Linux runner with Bash, Python 3 and Azure CLI |
| `timeout-minutes` | number | `60` | Plan and deploy job timeout |

### Environment variables

Set these as **variables** (not secrets) on each GitHub environment. They are identifiers, not
credentials.

| Variable | Required | Value |
| --- | --- | --- |
| `AZURE_CLIENT_ID` | yes | Client ID of this environment's app registration or user-assigned managed identity |
| `AZURE_TENANT_ID` | yes | Microsoft Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | yes | Target subscription ID |
| `TFSTATE_STORAGE_ACCOUNT` | Terraform | State storage account name |
| `TFSTATE_CONTAINER` | no | State blob container; `tfstate` when unset |

Rules for reusable workflows:

- A reusable workflow reads the **caller** repository's variables.
- An environment variable overrides repository and organization variables with the same name.
  Only jobs that declare that `environment` can see it.
- Workflow-level `env` in the caller does **not** propagate.
- A variable that is not set evaluates to an empty string. The workflow therefore checks every
  value before logging in.

See the [variables reference](https://docs.github.com/en/actions/reference/workflows-and-actions/variables)
and the [reusable workflow reference](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations).

The Terraform state key is `<working-directory>/<environment>.tfstate`, or
`<environment>.tfstate` for `.`. The backend uses Microsoft Entra authorization with the same
OIDC identity.

### Jobs

1. **preflight**: has no environment and no Azure access, and runs with `contents: read` and
   `actions: read`.
   - It validates the inputs.
   - It refuses `pull_request_target` runs and runs whose head comes from another repository.
   - It reads the environment through
     [`GET /repos/{owner}/{repo}/environments/{name}`](https://docs.github.com/en/rest/deployments/environments).
     A missing environment fails the run, so a typo cannot auto-create an unprotected
     environment.
   - Protected environments must have a required-reviewers rule with at least one reviewer.
     Otherwise, or if the API cannot answer, the run fails with the plan note below.
   - Protected environments also fail when *Prevent self-review* is off, when administrators can
     bypass the rules (or the API does not report `can_admins_bypass: false`), or when deployment
     branches are unrestricted. Each gap lets one person obtain the environment's Azure token
     without an independent review. The error lists every setting to change. Environments that
     are not protected, such as `dev` with `protected: false`, only need to exist.
2. **plan**: runs in `environment: {name, deployment: false}` with `id-token: write`. This job
   receives the environment's variables and OIDC subject without creating a deployment record.
   - Bicep: the job logs in, compiles `main.bicep` and the parameters, and runs
     `az deployment group what-if`.
   - Terraform: the job runs `init -lockfile=readonly` and `plan -out`.
   - The compiled files or the plan are uploaded with `retention-days: 1`; see
     [preview artifacts and secrets](#preview-artifacts-and-secrets).
3. **deploy**: runs in `environment: <name>`.
   - It downloads that artifact and re-checks the variables. It fails if
     `AZURE_SUBSCRIPTION_ID` changed after the preview.
   - Bicep: it runs `az deployment group create` with the same compiled template and parameters.
   - Terraform: it runs `terraform apply` on the saved plan. Terraform rejects a stale plan.
   - With `health-url`, it retries an HTTPS request for about three minutes and fails the
     deployment unless the URL answers `2xx`; a redirect fails it. Production ingress is private,
     so pass the public host fronting the app (operator-owned edge) or the private FQDN from a runner with network reach, for example `https://<host>/health/ready`. Behind Container Apps authentication, add that path to `excludedPaths`.

Concurrency is grouped per environment and never cancels a running deployment. As GitHub does
by default, a newer queued run replaces an older one that is still pending in the same group.
Azure CLI state is kept in `$RUNNER_TEMP`, and no job persists Git credentials.

### Approvals

Required reviewers and wait timers also apply to `deployment: false` jobs (see
[using environments without deployments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments)).
A protected environment is therefore approved twice:

- once before the preview runs; and
- once before deploy, after the what-if or plan output is visible.

The second approval is the review that matters. `deployment: false` is not compatible with
custom deployment protection rules, so environments that use protection-rule apps fail at the
preview. Use required reviewers instead.

There is deliberately no separate `<env>-preview` environment without reviewers. The delivery
validator and governance gate require the plan job to use the target environment with
`deployment: false`. A preview environment would also need its own identity, variables, branch
policy and read-only grant, and it would take the preview out from behind the reviewed
environment's approvals.

### Plan and visibility effects

| Repository | Free | Pro / Team | Enterprise |
| --- | --- | --- | --- |
| Public | Environments, variables, required reviewers, wait timers and branch policies | Same | Same |
| Private or internal | No environments: preflight fails | Environments, variables and branch policies; no required reviewers, so protected environments fail closed | All, including required reviewers |

Sources:

- [Managing environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
- [Deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)

Converting a Free repository from public to private makes GitHub ignore its protection rules.
The preflight check catches this instead of deploying unreviewed.

## Azure Pipelines

Reference the toolkit through an approved repository resource pinned to the reviewed 40-hex
commit, as described in [pinning templates](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/templates).

```yaml
trigger:
  branches:
    include: [main]
pr: none
resources:
  repositories:
    - repository: delivery
      type: github
      name: lfr-ai/agent-kit
      endpoint: <approved-github-connection>
      ref: <reviewed-full-sha>
extends:
  template: packages/delivery/azure-devops/extends/azure-deploy.yml@delivery
  parameters:
    environments:
      - { name: dev, serviceConnection: azure-dev, resourceGroup: rg-app-dev }
      - { name: test, serviceConnection: azure-test, resourceGroup: rg-app-test }
      - { name: prod, serviceConnection: azure-prod, resourceGroup: rg-app-prod }
```

Each environment item takes:

- `name`;
- `serviceConnection`;
- `resourceGroup` for Bicep, or `tfstateStorageAccount` for Terraform;
- optionally, `parametersFile` and `healthUrl` (the same post-deploy check as GitHub's
  `health-url`).

Shared parameters mirror the GitHub inputs: `iac`, `workingDirectory`, `image`,
`tfstateContainer`, `bicepVersion`, `terraformVersion` with `terraformSha256`, `vmImage` and
`timeoutMinutes`. `deployBranch` (default `refs/heads/main`) is the full ref allowed to preview
and deploy. `pool` (default `hosted`) selects a Microsoft-hosted `vmImage` agent; any other
value names a self-hosted or [Managed DevOps Pools](https://learn.microsoft.com/en-us/azure/devops/managed-devops-pools/overview)
agent pool, which private staging and prod networks need.

Azure Pipelines evaluates approvals and checks [before each stage starts](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/approvals).
The template therefore emits two stages per environment:

- `preview_<name>`: an ordinary job that publishes the what-if inputs or the saved plan.
- `deploy_<name>`: a `deployment` job that targets the Azure DevOps environment, downloads that
  artifact and applies it.

Stages run in list order. Both stages use [AzureCLI@2](https://learn.microsoft.com/en-us/azure/devops/pipelines/tasks/reference/azure-cli-v2)
with a [workload identity federation](https://learn.microsoft.com/en-us/azure/devops/pipelines/library/connect-to-azure)
service connection. Terraform receives that identity through
`ARM_OIDC_AZURE_SERVICE_CONNECTION_ID` and `System.AccessToken`, which is never printed. Fork
builds are refused.

Each `preview_<name>` and `deploy_<name>` stage runs only when all of these hold:

- the earlier stages succeeded;
- `Build.SourceBranch` equals `deployBranch`;
- `Build.Reason` is not `PullRequest`.

Otherwise the stage is skipped, not failed, and later stages skip too. The preview is gated as
well because a what-if or plan runs the caller's template code with the deploy identity.
Validate pull requests with the backend-less [bicep-check.yml](../azure-devops/extends/bicep-check.yml)
or [terraform-check.yml](../azure-devops/extends/terraform-check.yml) pipelines instead; they
use no service connection. The deploy step repeats the pull-request and branch tests in both
stages and fails if either does not hold. Both are defence in depth. The environment and
service connection checks (*Branch control*, *Approvals*, *Exclusive lock* and *Required
template*) remain the primary gate; see [Azure DevOps setup](#azure-devops).

## Preview artifacts and secrets

The preview artifact holds what deploy applies, so it must not carry secret values:

- Compiled `params.json` writes literal `@secure()` values in clear text. A `.bicepparam`
  `getSecret()` stays a Key Vault reference.
- A saved Terraform plan holds every input and state value, including ones marked sensitive.

Supply secrets through Key Vault references: Bicep `getSecret()`, Container Apps `keyVaultUrl`
secret references and managed identity. Never pass them as `-var` values or parameter-file
literals.

GitHub keeps the artifact for one day. Azure DevOps pipeline artifacts follow the run's
retention policy and cannot expire sooner, so set a short project retention and restrict who has
*View builds*.

## Terraform provider cache

Only the backend-less check pipelines, `.github/workflows/delivery-terraform-check.yml`
(repository root) and [terraform-check.yml](../azure-devops/steps/terraform-check.yml), use a
provider plugin
cache, keyed by the committed `.terraform.lock.hcl`. Deploy jobs never restore a cache.
`init -lockfile=readonly` still verifies provider hashes against the lock file, so a cached
provider that does not match is rejected.

## One-time operator setup

### Azure

1. Create one identity per environment: an app registration or a user-assigned managed
   identity. A dev identity must never reach test or prod. Prefer a user-assigned managed
   identity: it cannot hold a client secret or certificate. Create it in a separate resource
   group where CI has no role, so the deploy identity cannot add federated credentials to
   itself; see [deploy identity limits](identity-and-network.md#deploy-identity-limits).
2. Add federated credentials:
   - GitHub: issuer `https://token.actions.githubusercontent.com`, audience
     `api://AzureADTokenExchange`. Before configuring trust, verify the actual `sub`
     issued for the plan and deploy jobs against the repository's configured OIDC
     subject format. Do not assume `repo:<owner>/<repo>:environment:<name>` applies
     universally. Configure the federated credential to match the verified subject
     exactly; see the
     [OIDC reference](https://docs.github.com/en/actions/reference/security/oidc).
     Trust only the `environment:<name>` subject of that identity's environment. A branch,
     tag or pull-request subject mints the same token without the environment's reviewers;
     [bootstrap](bootstrap.md#github) `--access deploy` refuses them.
   - Azure DevOps: create the service connection with workload identity federation.
     Verify its configured issuer and actual subject, and match the federated
     credential to those values rather than deriving the subject from names.
3. Grant the least role at the narrowest scope. The exact roles, role IDs and the
   role-assignment condition are in [identity and network](identity-and-network.md#deployment-roles):
   - Bicep and Terraform: Contributor on the target resource group, plus Role Based Access
     Control Administrator constrained to the templates' data-plane roles and to service
     principals. [Bootstrap](bootstrap.md) `--access deploy` creates both.
   - Terraform also needs *Storage Blob Data Contributor* on the state container, which the
     [state composition](../infra/terraform-state) grants. Shared-key access to that storage
     account should be disabled.
   - Templates that create `CanNotDelete` locks (the starter does in staging and prod) also need
     a custom lock-writer role on the resource group: `Microsoft.Authorization/locks/read` and
     `locks/write`, no delete. Neither role above can write locks. Assign it before the first
     prod-like deploy; see [deletion locks](bootstrap.md#deletion-locks).

### GitHub

1. Create `dev`, `test` and `prod` before the first run, and set their variables.
2. On prod and any `protected` environment, configure these; preflight fails the run when any
   is missing:
   - add required reviewers;
   - enable *Prevent self-review*;
   - clear *Allow administrators to bypass configured protection rules*;
   - limit deployment branches to protected branches, or to selected branches such as the
     protected default branch. Preflight does not inspect the selected patterns, so do not
     select `*`.
3. Do not add custom protection-rule apps; they conflict with the preview.

### Azure DevOps

1. Pre-create the environments and restrict the *Creator* role. A deployment job that names a
   missing environment can otherwise [create it without checks](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/environments).
2. On every environment, add *Exclusive lock*; with the default `runLatest` lock behavior a
   newer run supersedes older pending ones without cancelling the running deployment. The
   lock gates only `deploy_<name>`; unlike the GitHub concurrency group, previews of separate
   runs may overlap. On prod, also add *Approvals* (disallow approving your own run).
3. On every `azure-<env>` service connection, add *Branch control* that allows only
   `deployBranch` and *Required template* that allows only the reviewed toolkit templates
   (`extends/azure-deploy.yml` at the pinned commit). Put approvals on the environment, not the
   service connection: a check on the connection gates the preview stage too, which already
   runs only from `deployBranch`.
4. On every environment, add *Branch control* that allows only `deployBranch`, and *Required
   template*. [Bootstrap](bootstrap.md#printed-ci-host-setup) `--emit azure-devops` prints a
   Branch control check for review.
5. Authorize each service connection for this pipeline only.
6. Use only *Workload identity federation* Azure Resource Manager service connections. The
   pipeline cannot read a connection's authentication scheme, so nothing in it detects a
   connection that uses a service principal secret or certificate; this is an operator control:
   - convert or delete secret- and certificate-based connections, and do not create new ones;
   - limit the *Creator* and *Administrator* roles on service connections to the people who
     review them;
   - back each connection with a user-assigned managed identity, which cannot hold a secret.
     For an app registration, have the tenant block password and certificate credentials with
     a [tenant app management policy](https://learn.microsoft.com/en-us/graph/api/resources/tenantappmanagementpolicy).

## Deployment mode decision

Resource-group deployments use incremental mode, which never deletes resources that are
missing from the template. Removing a resource is an explicit, reviewed change. Deployment
stacks were not chosen, for three reasons:

- Their `actionOnUnmanage` can delete resources.
- Deny settings need the *Azure Deployment Stack Owner* role.
- Deleting the resource group still bypasses their deny assignments, as listed in the
  [known issues](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deployment-stacks-known-issues).

A caller can adopt stacks in its own template process.

## Rollback and limits

**Roll back** by redeploying the last good commit or image digest: rerun its workflow or
pipeline, or revert and push. A failed health check leaves the new revision in place, so roll
back the same way. Azure resources created by a release are not removed by a Bicep rollback. Terraform
plans their removal from state, so review that plan. Reverting these sources cannot undo
deployments, Terraform state or approvals that already happened.

**Limits:**

- These paths are checked offline only. They are not exercised against GitHub, Azure DevOps or
  Azure.
- The GitHub path targets GitHub.com.
- Azure DevOps artifacts follow run retention, not a one-day expiry; see
  [preview artifacts and secrets](#preview-artifacts-and-secrets).
- Re-running a whole successful Azure DevOps preview stage conflicts with the published
  artifact name. Rerun failed jobs or start a new run.
- Approvers on public repositories should assume that preview artifacts are visible to readers
  for one day.
