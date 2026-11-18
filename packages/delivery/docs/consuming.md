# Consumer contracts

## GitHub

The [canonical workflows](integration.md) live directly under repository
`.github/workflows`. Consumers call
`lfr-ai/agent-kit/.github/workflows/delivery-python-ci.yml@<reviewed-full-sha>`
(or the corresponding Bun/Bicep/Terraform filename). The placeholder is not an
executable pin; select the reviewed published commit before adoption. Workflows
are call-only and do not add triggers to consumer repositories. The fifth
workflow, `delivery-azure-deploy.yml`, is the environment-gated deployment path;
see [Azure deployment](deploy.md) for its own permissions and setup.

- Grant check workflows only `contents: read`; they need no Azure login or
  `id-token: write`.
- Supply exact tool versions using the names in [catalog.json](../catalog.json).
- Python needs consumer-owned `pyproject.toml`, `uv.lock`, locked `go-task-bin`
  and a check-only Task target (`verify` by default).
- Bun needs consumer-owned `package.json`, `bun.lock` and a check-only script
  (`check` by default).
- Reusable CI has no coverage-upload inputs, secrets or upload step. Callers own
  any separate, isolated OIDC coverage-upload job, including its action/CLI pins.
  Do not grant upload credentials or OIDC permissions to these check-only jobs.

### Keeping later steps in the same Python job

The reusable Python workflow and toolkit CI share the native composite
[Python check action](../actions/python-check/action.yml). A caller that needs
subsequent packaging steps in the same job can use
`lfr-ai/agent-kit/packages/delivery/actions/python-check@<reviewed-full-sha>`
after a checkout with persistent credentials disabled. The action does not
check out or audit dependencies: complete the approved dependency audit before
invoking it.

Supply `python-version` and `uv-version`. The Task defaults to `verify`; its
name must be a single task, not arguments or command-line options. Missing or
floating versions fail before setup. The locked consumer environment must
include `go-task-bin`. Bash is required, including on Windows.

The toolkit and reusable workflow use GitHub.com's `$/` self-repository
reference, which binds the action to the running workflow's repository and
commit rather than mutable checked-out files. GitHub Enterprise Server does
not support this Python composition. See the official
[self-repository reference contract](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsuses).
File and shell tests do not certify hosted runner execution.

## Azure Pipelines

Reference a reviewed immutable repository revision through the consumer's
approved repository resource and use
`packages/delivery/azure-devops/extends/python-ci.yml@delivery` (or the other
check extends templates, or `extends/azure-deploy.yml` for
[deployment](deploy.md)). All subordinate template paths are self-relative.
Azure service connections, repository access and Required template checks remain
operator-managed. Do not remove environment approvals or branch policies.

Supply exact version parameters; Bun, Terraform and optional TFLint also require
the upstream Linux archive SHA-256. Update versions and checksums together.
Renovate's version regexes do **not** update these paired archive hashes.
The `jobs/python-task.yml` template, composed directly, optionally accepts a
consumer-owned hash-pinned `uvRequirementsFile`, and `preSteps` for private feed
setup through approved consumer secret mechanisms. The extends templates expose
only `extraSteps`. Never embed credentials. Built-in Azure task major versions are the upstream
Azure Pipelines convention, not immutable task implementation digests.

Azure Pipelines does not require a fixed folder. Keep consumer pipelines in
`.azuredevops/pipelines/`, the counterpart of `.github/workflows/`, where the
`kit-ci-pipelines` instruction applies. A minimal Python gate:

```yaml
# .azuredevops/pipelines/ci.yml
trigger:
  branches:
    include: [main]
pr:
  branches:
    include: [main]
resources:
  repositories:
    - repository: delivery
      type: github
      name: lfr-ai/agent-kit
      endpoint: <approved-github-connection>
      ref: <reviewed-full-sha>
extends:
  template: packages/delivery/azure-devops/extends/python-ci.yml@delivery
  parameters:
    pythonVersion: <exact-version>
    uvVersion: <exact-version>
```

Azure Repos ignores the YAML `pr` trigger. There, branch policies are the gate.
They live in project settings, not YAML, so script them once per repository.
The baseline mirrors the GitHub ruleset: one independent approval reset on push,
the CI build, resolved comments and a linked work item for traceability:

```bash
az repos policy approver-count create --repository-id "$REPO_ID" --branch main \
  --minimum-approver-count 1 --creator-vote-counts false --allow-downvotes false \
  --reset-on-source-push true --blocking true --enabled true
az repos policy build create --repository-id "$REPO_ID" --branch main \
  --build-definition-id "$CI_DEFINITION_ID" --display-name ci --valid-duration 720 \
  --queue-on-source-update-only true --manual-queue-only false \
  --blocking true --enabled true
az repos policy comment-required create --repository-id "$REPO_ID" --branch main \
  --blocking true --enabled true
az repos policy work-item-linking create --repository-id "$REPO_ID" --branch main \
  --blocking true --enabled true
```

A project that does not track work in Azure Boards can set the work-item policy
to `--blocking false`, which keeps it as an advisory reminder.

## Migrating an existing repository

Choose one path. A repository that keeps its own infrastructure code adopts the
templates as thin callers. Adopting the Copier starter replaces the service's
pipelines and infrastructure with the starter's.

### Existing project with its own IaC

1. Inventory the existing pipelines and delete steps that a template already
   covers: setup, lint, type check, tests, IaC checks and deployment.
2. Make the repository satisfy the template inputs: a locked `pyproject.toml`
   and `uv.lock` with `go-task-bin`, and a check-only `task verify`, or a
   `bun.lock` and `check` script.
3. Replace each pipeline with a thin caller pinned to one reviewed commit (the
   GitHub `uses:` call above, or the Azure Pipelines `extends:` example).
4. Move remaining repository-specific steps into `extraSteps` (or compose
   `jobs/python-task.yml` for `preSteps`); keep
   secrets in service connections or variable groups linked to Key Vault.
5. For IaC, keep your own templates and point the check callers and the
   [deployment](deploy.md) caller at them. Match the
   [caller repository layout](deploy.md#caller-repository-layout): `main.bicep`
   or a Terraform root with an empty `azurerm` backend and committed provider
   lock, one parameter file per environment (or `parametersFile`), and a
   `containerImage`/`container_image` parameter if you pass `image`. Keep the
   existing resource groups, state and registry; nothing is regenerated.
6. Set up the deployment identities, environments and checks once per
   environment as in [one-time operator setup](deploy.md#one-time-operator-setup),
   including Azure DevOps `deployBranch`, and run the caller's preview on the
   deploy branch to compare it with the current deployment before applying.
7. Run the callers on a branch, then make the check callers required (GitHub
   branch protection, or the Azure Repos build policy above) before removing the
   old pipelines.
8. Upgrade by bumping the pinned commit with the tool versions in
   [catalog.json](../catalog.json), never by following a branch.

### Starter adoption

New repositories get these callers from the Copier starter: `ci=github`
(default) emits GitHub workflows, `ci=azure-devops` emits
`.azuredevops/pipelines/` callers of these extends templates. An existing
service can adopt the starter's stack instead, but that also adopts its
application contract and Azure resources:

1. Generate the starter into an empty directory with the same `project_name`,
   `service=api`, your `iac`, `ci=github` or `ci=azure-devops` and
   `kit_commit=<tag commit>`.
2. Copy the generated pipelines (`.github/workflows/` or
   `.azuredevops/pipelines/`), the whole `infra/` directory, `scripts/` and
   `.copier-answers.yml` across. Fill in every parameter file, vendor Bicep
   modules or commit the Terraform provider lock, and reconcile the application
   with the starter's container contract (Dockerfile, port and health paths).
3. The starter's templates define their own resources and Terraform state keys
   (`infra/<environment>.tfstate`), unrelated to what your old IaC owns. Treat
   the first deploy as a new stack, not an in-place upgrade; never deploy both
   over the same resources without a reviewed ownership or state migration.
4. Set up CI: the GitHub environments and variables
   ([starter deployment](https://github.com/lfr-ai/agent-kit/blob/main/packages/starter/DEPLOYMENT.md#github-setup-and-execution)),
   or the `agent-kit-github` and `azure-<environment>` service connections and
   `<project>-<environment>` variable groups, pointing the existing pipeline
   definitions at the new YAML files
   ([setup](https://github.com/lfr-ai/agent-kit/blob/main/packages/starter/DEPLOYMENT.md#azure-devops-setup-and-execution)).
   Staging and prod also need the [lock-writer role](bootstrap.md#deletion-locks).
5. Keep the old image registry until the new per-environment ACR exists: run the
   registry bootstrap deployment first, then build and deploy.
6. Commit `.copier-answers.yml` so later upgrades can use `copier update`.

## Versions and upgrades

Delivery changes are recorded in the [delivery changelog](../CHANGELOG.md).
Releases are annotated tags named `delivery-vX.Y.Z` (Semantic Versioning) on a
reviewed `main` commit. Consumers still pin the **full commit SHA** the tag
points to: GitHub `uses:`, Azure Pipelines `ref:`, Terraform `?ref=` and the
starter's `kit_commit`. Tags are a reviewing aid, not a pin, because they can move.

| Change | Version part |
| --- | --- |
| Removed or renamed input, parameter, Copier answer or output; changed default behaviour | Major |
| New optional input, template, module or Copier answer with a compatible default | Minor |
| Fix without interface change | Patch |

Upgrade a generated project from its committed `.copier-answers.yml`:

```powershell
$commit = git -C ..\agent-kit rev-list -n 1 delivery-vX.Y.Z
uv run --locked --no-sync copier update --vcs-ref delivery-vX.Y.Z --data kit_commit=$commit
```

Then re-vendor Bicep modules from a checkout at that commit
(`python scripts/vendor_bicep.py --kit-checkout ..\agent-kit` into a fresh
`infra/vendor/`), or review Terraform module refs and the provider lock, and run
the generated project's checks before merging. Read the changelog's
**Upgrade notes** first. New answers take their defaults: a starter generated
before `registry` existed becomes `registry=acr` unless you pass
`--data registry=ghcr`.

## IaC checks are not deployment

Bicep formats, lints and compiles `.bicep` and `.bicepparam` files. Consumer lint
severity comes from `bicepconfig.json`; the templates fail on an empty source tree.
Terraform formats, initializes with `-backend=false -input=false -lockfile=readonly`,
then validates. Consumers own provider locks and backend/state configuration.
The check templates run no plan, apply or deployment; the separate
[Azure deployment](deploy.md) path previews and applies with OIDC behind
environment approvals.

**Hosted setup is not offline:** tool downloads, Bicep module restoration,
Terraform provider/module installation and optional TFLint initialization may
use network. Local proof uses only installed tools and synthetic files without
resources, providers or remote modules.

`run-tests` / `runTests` remains false by default. `terraform test` can apply
resources; enable it only for reviewed plan/mock-only suites under this check-only
contract. Extra steps and consumer Task/Bun scripts can also do arbitrary work;
review them before running, especially in privileged environments.

## Renovate

Vendor the reviewed JSON presets into consumer-managed configuration or publish
them through an explicitly approved preset mechanism later. These files are not
registered remotely. Merge the baseline with chosen technology presets; keep the
7-day age gate, strict checks and dashboard approval for majors. Consumers choose
their timezone. No automerge or hosted Renovate runner is enabled by this import.
