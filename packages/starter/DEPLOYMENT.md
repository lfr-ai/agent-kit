# Starter Azure deployment

This slice generates cloud sources only for `service=api` with `iac=bicep` or
`iac=terraform`. `iac=none` emits neither `infra/`, a vendor script, nor a deploy
workflow. `service=none` never emits cloud sources, even when IaC guidance is
selected. Generation performs no fetch, installation, login, build or deployment.

## Trust and ownership

Supply a reviewed, published `kit_commit`: exactly 40 lowercase hexadecimal
characters, not all zero. The same commit pins the reusable checks, deployment
workflow and Terraform module sources. Syntactic validation cannot establish
review or publication; the operator must confirm that the commit contains the
delivery modules, workflows and action closure before adopting it.
The commit must include the environment-map, existing-workspace and action-group interfaces
described here. An older immutable module revision will not acquire these inputs:
review a new full SHA and regenerate/re-vendor from that exact checkout; never
copy dirty module files or replace the pin with a branch.

The generated stack has **dev, test, staging and prod** parameter files with an
explicit matching `stage`. Local remains cloud-independent Compose, never a cloud
dispatch choice. Caller-owned `infra/<stage>.bicepparam` or
`infra/<stage>.tfvars` supplies distinct names and, for Terraform, the target
resource group ID. The region defaults to that explicitly selected resource group;
no region or subscription is guessed. This is not production certification.
Replace every `REPLACE_` value; dispatch refuses unfinished parameters before
building an image. Keep resource names distinct from other stacks. Terraform and
Bicep are alternatives: never deploy both over the same resources without an
approved ownership/state migration.

The stack creates a user-assigned **runtime identity** (`<prefix>-identity`) and
an application **telemetry workspace** (`<prefix>-telemetry`), then the existing
delivery modules create:

- Container Apps environment and application, sending console/system logs to
  the stack-owned workspace; HTTPS-only ingress, port 8080, health probes and
  consumption capacity.
  Dev/test use public application ingress and zero-to-three replicas.
  **Staging is production-like:** staging and prod (`prodLike` in Bicep,
  `local.prod_like` in Terraform) use an **internal environment**, disabled
  public network access, zone redundancy, two-to-three replicas and deletion
  protection (a resource lock). App `ingress.external=true` means VNet clients can
  reach this internal environment, not that it is Internet reachable. Cost
  choices stay explicit per parameter file (for example `registrySku`,
  `registry_sku` and alert receivers); prod-like hardening is not a toggle.
  Shared data and AI modules still receive the real stage, so their own
  prod-only defaults (such as their locks) apply to prod only.
- With `telemetry=application-insights`, workspace-based Application Insights
  and a Monitoring Metrics Publisher role assignment to the runtime identity.
  The default `telemetry=none` omits Insights and its exporter wiring, not
  console diagnostics or platform alert rules.
- An optional email action group and restart/HTTP 5xx metric alerts, or those
  alerts referencing an existing caller-owned group (Teams, email or both).
  Staging and prod require a destination; dev/test can explicitly opt out.
- Selected PostgreSQL and/or text AI resources through their shared modules;
  `none` creates none of those resources. `ai=true` alone adds guidance only.

PostgreSQL is private in every cloud stage, including dev, so no broad firewall
exception is needed. Text AI uses an Entra-only public endpoint in dev and private
endpoints in test/staging/prod. A VNet exists only for those private resources or
the staging/prod internal app, so staging always needs a reviewed,
non-overlapping CIDR; supply one for other stages when needed.
Only selected private-service DNS zones are created, using network outputs
`appsSubnetResourceId`, `privateEndpointSubnetResourceId` and the
`postgresql`/`cognitiveServices`/`openai`/`aiServices` DNS keys (snake_case in
Terraform).

The internal staging/prod app has its default-domain private DNS zone and wildcard
and apex A records linked to its VNet. This is **not** the `containerApps`
Private Link zone: no redundant app private endpoint is created. The foundation
still supports the separate Private Link topology for existing callers.
Use reviewed VNet peering, DNS forwarding and runner placement for remote clients.
ACA supplies TLS termination and load balancing; no nginx or certificate service
is added.

**Azure Redis is blocked:** the currently reviewed Entra integration has an
unresolved token-renewal shutdown lifecycle. `cache=redis` with cloud IaC fails
generation explicitly; it neither provisions a cache nor falls back to keys.
Use `iac=none` for existing local Redis behavior until a supported runtime path
is reviewed. No cloud-cache readiness is claimed.

The target resource group, PostgreSQL Entra administrator (when selected), and
any referenced action group must already exist. Owning the runtime identity
and telemetry workspace in the stack lets the Insights role assignment precede the
app without a dependency cycle. Deployment identity and runtime identity are
different principals. The deployment principal needs resource-group Contributor
and constrained authority for the Insights role assignment; do not grant
subscription-wide Owner merely to make deployment succeed. The separate
[Azure bootstrap](../delivery/docs/bootstrap.md) is offline by default and
operator-owned. Its `--access deploy` level grants exactly that pair: Contributor
plus a Role Based Access Control Administrator assignment constrained to a
reviewed role list (including Monitoring Metrics Publisher and Key Vault Secrets
User) for service principals. Its default `--access read` (Reader) is **not
sufficient** to deploy. Terraform state access is a separate, scoped grant.

With `telemetry=application-insights`, the stack supplies
`APPLICATIONINSIGHTS_CONNECTION_STRING` and `AZURE_CLIENT_ID`. The generated API
explicitly configures trace export, authenticating ingestion as the runtime
identity through `ManagedIdentityCredential`. It does not start a duplicate
FastAPI instrumentor or export SDK logs/metrics. Without an endpoint, local
startup does not load Azure telemetry or credentials. Console records carry
`trace_id` when a trace is active. Provisioning does not prove arrival: verify
actual spans and correlated logs in the deployed environment.

New environments share the stack's `<prefix>-telemetry` workspace between
console/system logs, optional Insights and selected service diagnostics. Its
diagnostic retention is 30 days; retention, access and resource protection
belong to the stack, not to the ACA module using it. Query console records in
`ContainerAppConsoleLogs_CL`; optional Insights operation IDs correlate with
console `trace_id`. Alert rules use platform metrics and do not depend on
Insights or workspace ingestion.

**Existing environments are not automatically migrated.** The standalone ACA
module still defaults to its dedicated workspace; an explicitly supplied
existing workspace is never recreated or locked by that module. Before updating
an older generated two-workspace stack:

1. Inventory both workspace IDs, resource/state addresses, diagnostic settings,
   Insights association, locks, RBAC, retention and all other consumers.
2. Keep the old composition until shared retention/access/residency is approved.
   Generate the new revision separately and review the complete plan/what-if.
3. Preserve identities and use reviewed Terraform moved/import or ownership
   transitions. Do not simply remove an owned workspace from Terraform
   configuration: that can schedule deletion. Bicep incremental omission leaves
   it behind and does not transfer ownership.
4. Redirect new ingestion only after the destination and permissions are ready.
   Historical data is not copied by changing a diagnostic destination.
5. Retain query access to old workspaces for their retention and rollback
   obligations. Their eventual deletion is a separate operator decision.

Diagnostic retention is not an audit-retention or immutable-storage guarantee.

Structured console records persist centrally across container restarts within
the configured retention. Live streaming is not historical storage, and
collection is not guaranteed lossless. There is one sanitized access record per
request; a separate problem event adds failure attribution. SDK log export and
ingress HTTP logging are not enabled. Failures before application middleware have
no application access record. The two alerts use platform metrics independently
of log collection; see the [delivery test procedure](../delivery/infra/container-apps-alerts/REFERENCE.md).

## Bicep: offline, immutable vendoring

The generated `scripts/vendor_bicep.py` accepts an explicitly supplied toolkit
checkout whose `HEAD` equals `kit_commit`. It reads only `git cat-file` blobs at
that commit, never working-tree files, the index, a branch tip or an ambient
toolkit path. Dirty working-tree changes cannot enter the vendor output. Git lazy
fetch is disabled; absent objects fail without fetching.

Run in the generated consumer with an already installed Python and Git:

```powershell
python scripts/vendor_bicep.py --kit-checkout ..\agent-kit
python scripts/vendor_bicep.py --check
bicep format infra/main.bicep --stdout
bicep lint infra/main.bicep --no-restore
bicep build infra/main.bicep --no-restore --stdout
bicep build-params infra/dev.bicepparam --no-restore --stdout
```

Commit the entire resulting `infra/vendor/` tree, including `LICENSE`,
`PROVENANCE.md` and `manifest.json`. The manifest records the repository, commit,
source paths and SHA-256 of every blob. No ambient checkout is needed afterwards;
the root compiles after relocation. CI verifies the exact vendor inventory and
hashes before the reusable Bicep check. The manifest is a reviewed integrity
record, not an external signature: changing it together with the sources requires
a new source review. Reproduce from the reviewed checkout to verify authenticity.
Existing output is never overwritten; review a separately generated tree for an
upgrade. Do not copy uncommitted toolkit files into `vendor/`.

The workflow pins Bicep `0.48.1`. `using none` lets the parameter file omit the
image; the existing deployment workflow injects the built digest after compiling
parameters. This also means standalone parameter compilation is not full
parameter-to-template validation.

## Terraform: immutable modules, caller-owned state

The root pins Terraform `1.16.7`, AzAPI `2.13.0`, and all selected delivery modules
with full-SHA Git URLs. It declares an empty `azurerm` backend. No provider lock is
fabricated by Copier. An approved operator must initialize the generated root,
review and commit its platform-appropriate `.terraform.lock.hcl`, and provision
the state backend before dispatch. CI and deployment fail closed without the
lock. Provider bootstrap and module retrieval can use network; they are not part
of this offline authoring task.
Follow the single [state-backend bootstrap procedure](../delivery/infra/terraform-state/README.md);
the identity bootstrap does not create backend storage.

With the required providers/modules already installed for this root:

```powershell
$env:CHECKPOINT_DISABLE = '1'
terraform -chdir=infra fmt -check -recursive -diff
terraform -chdir=infra validate -json
```

Do not claim provider validation from formatting or variable-only validation.
Do not run `init` as an offline check unless using an explicitly provisioned
mirror and module cache with network disabled.

The existing deployment workflow owns initialization, preview, approval and
application of the saved plan. It uses Entra/OIDC backend access with separate
state keys `infra/dev.tfstate`, `infra/test.tfstate`, `infra/staging.tfstate` and
`infra/prod.tfstate`. State account/container are environment variables, not source
values. Never commit `.terraform/`, plans, state or credentials. Back up state
through the caller's approved process; changing IaC selection does not migrate it.

## GitHub setup and execution

1. Review and commit application locks, parameters, vendor files or provider lock.
   The generated app's own `task ci` remains the application gate.
2. Create and protect each selected **dev/test/staging/prod** environment with required reviewers,
   *Prevent self-review*, cleared *Allow administrators to bypass configured protection rules*
   and deployment branches limited to *Protected branches only* or *Selected branches and
   tags* (reviewed `main`). This starter calls delivery with `protected: true`; the preflight
   fails, naming each missing setting, when protection cannot be verified.
   Availability of required reviewers depends on the repository's GitHub plan.
3. Configure environment variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and
   `AZURE_SUBSCRIPTION_ID`; Terraform also needs `TFSTATE_STORAGE_ACCOUNT` and
   optionally `TFSTATE_CONTAINER` (default `tfstate`). Set up environment-scoped
   OIDC federation and least-privilege Azure roles out of band. Staging and prod
   create `CanNotDelete` locks, which Contributor and the constrained RBAC
   administrator cannot write: before their first deploy, assign the lock-writer
   custom role from [deletion locks](../delivery/docs/bootstrap.md#deletion-locks).
4. For Bicep, set the **repository** variables `AZURE_RESOURCE_GROUP_DEV`,
   `AZURE_RESOURCE_GROUP_TEST`, `AZURE_RESOURCE_GROUP_STAGING` and
   `AZURE_RESOURCE_GROUP_PROD` for the environments you use. Each names its existing
   target group. A reusable-workflow call cannot read variables scoped
   to an environment that only the called job declares. The region defaults to
   that group.
5. Explicitly dispatch **Deploy environment** on reviewed `main`, choosing a cloud
   stage and a reviewed Linux runner label. Private data-plane checks and PostgreSQL
   bootstrap require VNet/DNS access; the exposed `runs-on` input passes through to
   the existing reusable workflow. Checks run first; a
   read-only intent check also rejects unfinished parameters and a nonliteral or
   mismatching parameter stage. With `registry=acr` it reads the environment's
   registry name from the parameters; with `registry=ghcr` it requires the public
   image acknowledgement. Exactly one call to the Image workflow builds,
   pushes and attests the image for this deployment run. With GHCR, a separate job
   then verifies anonymous access to that exact manifest digest, without a stored login.
6. Only then does the pinned `delivery-azure-deploy.yml` receive the image output
   unchanged. It previews and applies the same compiled Bicep files or saved
   Terraform plan, behind its existing environment controls. There is no second
   apply engine in the starter.

PR CI has `contents: read` only, no environment and no OIDC or deployment
identity. Deployment has **no PR, push or workflow-run trigger**. With GHCR, the Image
workflow deliberately retains its independent push/manual/call behavior;
therefore a push build and a later explicit dispatch can produce separate images,
but a deployment never substitutes that unrelated image for its own digest. With
ACR, the Image workflow is call-only.

## Image registry

The `registry` answer applies to `service=api` with cloud IaC.

**`acr` (default).** Each environment's stack owns an Azure Container Registry
through the delivery `container-registry` module. Names come from
`registryName`/`registry_name` in each parameter file (5-50 lowercase letters and
digits, globally unique: change the generated value if it is taken), and
`registrySku`/`registry_sku` picks Basic or Standard for dev/test, and the
starter requires Premium for staging/prod because private endpoints need it (a
Premium dev/test registry would deny public pulls without a private endpoint, so
it is rejected too). Admin user and
anonymous pull are disabled. The runtime identity gets **AcrPull**, the
deploying principal gets **AcrPush**, and the app pulls through
`registryServer` with that user-assigned identity; no registry password exists.
Staging/prod registries are private (private endpoint and `containerRegistry` DNS
zone) and use the module's prod stage, so they also get its lock and retention.

- The image job runs in the selected GitHub environment with `id-token: write`,
  logs in with `azure/login` (OIDC) and `az acr login`, pushes with Buildx,
  attaches BuildKit provenance/SBOM metadata and a GitHub digest attestation, and
  returns `<registry>.azurecr.io/<repo>@sha256:...`.
  The protected environment therefore asks for approval three times per run: the
  image job, the delivery preview (a `deployment: false` job in the same
  environment) and deploy, after the what-if or plan is visible; see
  [delivery approvals](../delivery/docs/deploy.md#approvals). A
  `registry-bootstrap` run skips the image job and asks twice.
- Staging/prod pushes need a runner with network access to the private registry:
  pass that runner label as `runs-on`.
- **Registry bootstrap.** The first deployment of an environment has no registry
  to push to. Dispatch once with `registry-bootstrap` set: the image job is
  skipped and the stack deploys the registry, network and shared resources
  without the app and alerts. Then dispatch again normally. Bicep never removes
  an existing app in incremental mode; the Terraform root refuses an empty image
  once `<prefix>` already has an app, so bootstrap cannot destroy it.
- The AcrPush grant uses the deploying principal as a service principal, so
  deploy through CI, not as a user. [Bootstrap](../delivery/docs/bootstrap.md)
  `--access deploy` already allows AcrPush and AcrPull in its constrained role list.

**`ghcr`** keeps the public GHCR path and is for **dev or evaluation only**: the
image must be publicly readable, as described below. Do not use it for staging
or prod workloads that need private images.

## Azure DevOps setup and execution

With `ci=azure-devops`, no `.github/` directory is generated. Instead:

| File | Purpose |
| --- | --- |
| `.azuredevops/pipelines/ci.yml` | PR and main quality gate; extends `python-ci.yml` |
| `.azuredevops/pipelines/iac.yml` | Check-only Bicep or Terraform gate; extends `bicep-check.yml` or `terraform-check.yml` |
| `.azuredevops/pipelines/image.yml` | Manual build and push to the selected environment's ACR; prints the digest |
| `.azuredevops/pipelines/deploy.yml` | Manual preview then deploy of one environment; extends `azure-deploy.yml` with `deployBranch: refs/heads/main` |

Every pipeline references the toolkit through repository resource `delivery`
pinned with `ref: <kit_commit>`. Azure DevOps deployment supports `registry=acr`
only. The pinned commit must contain the `deployBranch` and `pool` parameters of
`extends/azure-deploy.yml`.

1. Create a GitHub service connection named `agent-kit-github` (or edit `endpoint`)
   and authorize it for these pipelines only.
2. Create one workload identity federation Azure Resource Manager service connection
   per environment, named `azure-<environment>`, with the roles described above,
   authorized for `image.yml` and `deploy.yml` only. For staging and prod, also
   assign the lock-writer custom role from
   [deletion locks](../delivery/docs/bootstrap.md#deletion-locks) before the first
   deploy; the stack's `CanNotDelete` locks otherwise fail with `AuthorizationFailed`.
3. On every `azure-<environment>` service connection, add *Branch control* (allow
   only `refs/heads/main`, require branch protection) and *Required template*
   (`packages/delivery/azure-devops/extends/azure-deploy.yml` from the pinned
   `delivery` repository). Keep approvals off the connection: its checks gate the
   preview stage and `image.yml` too.
4. Pre-create the `dev`, `test`, `staging` and `prod` environments with *Approvals*,
   *Exclusive lock*, *Branch control* and *Required template*, as in the
   [delivery setup](../delivery/docs/deploy.md#azure-devops). Environment approvals
   gate the `image.yml` job and the deploy stage, so a release asks twice; the
   preview stage passes only the connection checks.
5. Create variable group `<project>-<environment>` per environment with
   `AZURE_RESOURCE_GROUP` (Bicep) or `TFSTATE_STORAGE_ACCOUNT` (Terraform).
6. Make `ci.yml` and `iac.yml` required build policies on `main`, together with the
   approver, comment-resolution and work-item-linking policies in the
   [branch policy baseline](../delivery/docs/consuming.md#azure-pipelines).
7. To deploy, run `image.yml` on `main` for the environment (select an agent pool
   with private-registry access for staging/prod), copy the printed digest, then
   run `deploy.yml` with that `image` and, for staging/prod, the same private
   `pool`. For the first deployment of an environment, run `deploy.yml` with
   `registryBootstrap` set before building the image.

**Known gap: `image.yml` extends no toolkit template yet.** It is an inline
deployment job, so the *Required template* checks in steps 3 and 4 block its
runs, and its main-only test is pipeline YAML that a branch can edit. Until the
toolkit ships an image extends template, choose per environment: keep *Required
template* and push images through another reviewed path, or leave it off and
rely on *Branch control* (with branch protection on `main`), the per-pipeline
connection authorization and environment approvals.

Unlike GitHub, the digest is handed over manually, because the delivery deploy
template has no image-build stage. The deploy template rejects anything other
than a `registry/repository@sha256:` digest, and Terraform additionally requires
the environment's own registry.

### GHCR private pull is not implemented

This applies to `registry=ghcr` only.
GHCR packages may be private on first publication. A successful authenticated
push does not mean Container Apps can pull the image. Azure's managed-identity
pull support here is for **ACR**, not GHCR, and the delivery module has no GHCR
username/password input. No GitHub token is passed to the runtime.

For this generated workflow, the operator must explicitly approve public image
disclosure, publish once through the standalone Image workflow if needed, and
manually configure the package as publicly readable. Dispatch defaults the
`public-ghcr` acknowledgement to false; even an acknowledgement cannot bypass the
anonymous digest check. **No workflow changes package visibility.** If the image
must remain private, regenerate or update with `registry=acr`. Do not make
private application images public merely to satisfy the starter.

## Alerts and existing receivers

Alert destinations are caller-owned environment **parameter-file configuration**,
not Copier answers. Set `alertEmailReceivers` / `alert_email_receivers` to create
an email-only group, or supply `alertActionGroupResourceId` /
`alert_action_group_resource_id` for an existing Azure Monitor action group.
The latter is preferred for Teams and can include email or Logic Apps receivers
too. These destinations are mutually exclusive; no transport selector is needed.
The module never reads, imports or modifies an existing group.

The operator configures/enables/tests the receivers in the existing group and
owns that resource and its workflow connections. An ID alone cannot prove a Teams
receiver exists or can deliver. Establish an incident owner and test the actual
receiver using the action group's Test feature and a controlled non-production
failure; see the [operator procedure](../delivery/infra/container-apps-alerts/REFERENCE.md).
No new relay is built. No raw Teams webhook is accepted in Copier answers,
per-env parameters, state or preview artifacts, nor is the receiver payload read
back into the stack. Missing or conflicting destinations fail explicitly.
Dev/test parameter files opt out through `alertsUnmonitored=true` /
`alerts_unmonitored=true`: rules still exist but notify nobody. To connect
notifications, set it false and provide a destination. Staging/prod prohibit opt-out and contain an existing-group
placeholder that must be replaced before dispatch.

For example, in the caller's Bicep environment file:

```bicep
param alertsUnmonitored = false
param alertEmailReceivers = []
param alertActionGroupResourceId = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/alerts/providers/Microsoft.Insights/actionGroups/operations'
```

Or in Terraform:

```hcl
alerts_unmonitored             = false
alert_email_receivers          = []
alert_action_group_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/alerts/providers/Microsoft.Insights/actionGroups/operations"
```

These are synthetic IDs: replace them with reviewed, existing resources. Changing
from an already deployed inline-email group to an external group is a separate
ownership transition. Terraform will plan deletion of the former owned group;
Bicep incremental deployment leaves it behind. Do not reference the same former
group as "external" without an approved state/ownership migration.

## Application settings and existing resources

With cloud IaC, `data=postgresql` and `ai_service=text` now select both application
integrations and shared-module provisioning. `auth=entra-bearer` still requires a
caller-owned app registration and trust settings. `cache=redis` is blocked for
cloud IaC as described above. Local behavior is unchanged.

Use `environmentVariables` / `environment_variables` for additional nonsecret
**string** settings, and `secretReferences` / `secret_references` for credentials
backed by existing Key Vault secrets. Both default to empty. Caller settings and
secret destinations cannot collide with provisioner-owned connection/identity
settings, ignoring case. Collisions fail validation; there is no overwrite
fallback, including for the selected services' password/API-key slots.
`APP_ENVIRONMENT` is required by the runtime and always provisioned as the exact
cloud stage; it is reserved in both user maps. Local Compose uses `local`.

The API starter also emits secret-free `.env.dev.example`, `.env.test.example`,
`.env.staging.example` and `.env.prod.example`, in addition to the local
`.env.example`. Copy one to `.env` explicitly for a host-process run; process
environment values still take precedence. Stage files are not auto-selected or
merged. Cloud PostgreSQL/AI examples use explicit managed identities without
password/API-key slots; non-Azure examples keep password/key authentication and
remote TLS. Fill empty required fields from approved outputs and secret stores.
These files neither provision nor deploy anything and are not uploaded by the
pipelines. Deployed apps keep the IaC-injected configuration described below;
local Compose is not a staging/production deployment path.

| Selection | Nonsecret environment settings | Key Vault-backed environment destinations |
| --- | --- | --- |
| Provisioned PostgreSQL | Generated `APP_POSTGRES_HOST`, `APP_POSTGRES_DATABASE`, `APP_POSTGRES_USER`, `APP_POSTGRES_ENTRA_AUTHENTICATION=true`, `APP_POSTGRES_MANAGED_IDENTITY_CLIENT_ID` | None; password authentication is disabled |
| Azure Redis | Unsupported pending runtime lifecycle review | No key fallback |
| Entra bearer | `APP_AUTH_TENANT_ID`, `APP_AUTH_CLIENT_ID`, `APP_AUTH_AUDIENCE`, `APP_AUTH_ORIGIN`; `APP_AUTH_SCOPES` / `APP_AUTH_ROLES` JSON arrays with at least one permission | None; do not substitute the runtime identity for the API's trust configuration |
| Provisioned text AI | Generated `APP_AI_API_BASE` (OpenAI v1 endpoint), `APP_AI_MODEL=openai/<deployment>`, `APP_AI_ENTRA_AUTHENTICATION=true`, `APP_AI_MANAGED_IDENTITY_CLIENT_ID` | None; API key/version inputs are rejected |

Encode arrays/objects as strings, not nested IaC objects. Deploy once without
secret references, then grant the stack's `runtimeIdentityPrincipalId` /
`runtime_identity_principal_id` output Key Vault Secrets User at the approved
vault/secret scope, verify vault DNS/network reachability, and add the
references. A revision whose identity cannot read a referenced secret fails to
start. Deploying a secret URL does not grant access or read its value into the
template. Existing secrets remain caller-owned; selected service resources belong
to this stack. The deployment identity needs reviewed authority for AI role
assignments as well as telemetry; default bootstrap role constraints may need an
explicit operator-approved extension. Never grant broad Owner as a shortcut.

### PostgreSQL database-role bootstrap prerequisite

The stack assigns its runtime identity to ACA and configures a **separate,
caller-selected Entra administrator** on PostgreSQL. It does not silently grant
the app administrator rights. A client ID, ARM role assignment or successful IaC
apply does **not** create a database principal. Initial app readiness can fail
until this explicit data-plane step is completed.

Connect over TLS from a network/DNS-authorized host as that Entra administrator.
Using the identity name `<namePrefix>-identity` and the stack's
`runtimeIdentityPrincipalId` / `runtime_identity_principal_id` output, create
the service principal mapping with PostgreSQL's
`pgaadauth_create_principal_with_oid('<identity-name>', '<principal-object-id>',
'service', false, false)`. Run it in the server's `postgres` database, then grant
CONNECT on the selected application database. In that database grant USAGE on
the application schema and only the required table/sequence privileges; migration
ownership and default privileges belong to the separately reviewed migration
role. Do not grant the app superuser, database ownership or administrator status.
Verify the mapping and grants before retrying readiness. This scaffold cannot
claim an unattended first run, and no new bootstrap wrapper is provided.

### Text AI configuration

The caller supplies model, pinned version, deployment SKU and capacity explicitly;
regional availability/quota must be checked by the operator. The generated endpoint
is the module's `https://<name>.openai.azure.com/openai/v1/`, not the project endpoint.
Its Entra audience is `https://ai.azure.com/.default`. The generated runtime uses
per-inference async token acquisition with timeout and credential cleanup; no
API key or API version is supplied for v1. Live inference remains operator work. No inference
call or quota verification is made by rendering or offline tests.

Example Bicep values (add only settings for the app's selected services):

```bicep
param environmentVariables = {
  APP_AUTH_SCOPES: '["read"]'
}
param secretReferences = []
```

Equivalent Terraform fields:

```hcl
environment_variables = {
  APP_AUTH_SCOPES = jsonencode(["read"])
}
secret_references = []
```

These examples show encoding, not a complete configuration for every selection.
Names must match `[A-Za-z_][A-Za-z0-9_]*`. Duplicate secret destinations, overlaps
between plain and secret settings, and the six module-owned telemetry names are
rejected. The telemetry names stay reserved even while export is disabled.
Environment-name uniqueness, reserved-name and credential-slot checks ignore case
across both inputs while preserving accepted names, including single lowercase
nonsecret settings.
Credentials such as `OTEL_EXPORTER_OTLP_HEADERS` must use Key Vault references,
never the plain map. Provisioned-service credential slots are rejected in both
maps rather than overriding managed identity. Other arbitrary values cannot be
classified as secret automatically; callers must review them before committing
parameters or uploading previews.

## Rollback and offline evidence

Before deployment, roll back paired canonical module and generated-root changes
together so their interfaces stay compatible. The alerts child module's
`moved` block preserves its old owned group address; there is no general
root-level migration block. Other ownership changes require reviewed
`moved`/import operations. A source downgrade can require a reverse address
migration.
The standalone Image workflow was not changed. No live state or resource was
created by this task.

After operator deployment, reverting source does **not** undo resource creation,
image publication, role assignments, accumulated telemetry, public image
disclosure or Terraform state changes. Switching `registry` from `ghcr` to `acr`
adds a registry, AcrPull/AcrPush assignments and, for staging/prod, locks;
switching back does not remove them, and prod-like locks block deletion until
an approved operator removes them. Restore a previously reviewed digest and
configuration through the same preview/approval path; do not destroy resources or
delete state as a rollback shortcut. A publicly disclosed image cannot be made
undisclosed again. Review removals, log retention and role-assignment ownership
separately. Production availability, private topology and deletion locks must not
be downgraded as a rollback shortcut. Changing an existing ACA environment to
internal networking can require replacement: review migration, DNS, traffic and
data retention before applying. Splitting an existing dev state does not migrate
its resources into the other environments. Never copy a state file to create a
new environment.

Run the relevant checks from the toolkit's already provisioned environment:

```powershell
uv run --locked --no-sync python -m pytest `
  tests\integration\delivery\infra\test_container_apps.py `
  tests\integration\delivery\infra\test_container_apps_alerts.py `
  tests\integration\starter\test_iac.py `
  tests\integration\starter\test_deploy.py -q
task verify
```

The tests cover invalid/reserved/colliding environment names, compiled setting
and secret-reference forwarding, existing-group conflicts, no-IaC omission,
immutable module references and generated formatting. Workflow checks include
permission policy, Bash syntax and mocked public/private anonymous-pull responses
for GHCR, the ACR bootstrap/deploy ordering, and Azure DevOps parameter names
against the delivery extends templates.
These are not hosted runs. Keep temporary test output outside the checkout.

Tests simulate pinned Git blob responses from current delivery sources for
relocation compilation; this is **not** certification of a published kit commit.
Operator review/publication and a real-commit vendoring replay remain required.
A separate read-only Git test proves committed MIT license blobs can be
read while working-tree byte reads are forbidden. Native tool versions differ;
an older installed compiler is not certification of the workflow's pinned CLI.
`STARTER_TERRAFORM_CACHE` may point to a matching, already initialized
`.terraform` directory for offline provider validation; set `STARTER_KIT_COMMIT`
to its reviewed module commit (otherwise tests use a synthetic SHA).
`CONTAINER_APPS_AZAPI_MIRROR` (a reviewed AzAPI `2.13.0` plugin directory) enables
mocked first-apply plans of generated roots against working-tree modules: the
minimal stack, and PostgreSQL plus AI selected for each of `dev`, `test`,
`staging` and `prod`. They prove the stack-owned identity keeps module counts
known and that the stage, network and keyless AI settings reach the plan.
Missing caches or `actionlint` are explicit skips, never automatic installations.
Only installed module/provider code is copied into the test sandbox; backend
metadata and cached state are not copied.
Provider-backed tests for both canonical modules also require the reviewed
AzAPI `2.13.0` mirror; providerless validation is not a substitute. No provider
installation, hosted workflow, cloud query, preview or apply was performed.

## Official behavior references

- [GitHub reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows):
  workflow calls, outputs and permission constraints.
- [GitHub variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables):
  repository/environment variable scope.
- [GitHub Container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry):
  authentication, package visibility and anonymous public pulls.
- [Azure managed-identity image pulls](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull):
  ACR pull authorization; it is not GHCR authentication.
- [Azure Monitor action groups](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/action-groups):
  email receivers and webhook/Logic Apps transport.
- [Container Apps environment variables](https://learn.microsoft.com/en-us/azure/container-apps/environment-variables):
  plain settings, secret references and last-wins duplicate behavior (rejected here).
- [Container Apps secrets](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets):
  Key Vault references and runtime managed-identity prerequisites.
- [Metric alert action references](https://learn.microsoft.com/en-us/azure/templates/microsoft.insights/2018-03-01/metricalerts):
  action group resource IDs rather than receiver payloads.
- [Terraform sensitive data](https://developer.hashicorp.com/terraform/language/manage-sensitive-data):
  sensitive values can remain in state and plan files.
- [Delivery contract](../delivery/docs/deploy.md): exact inputs, OIDC, preview
  artifacts, state key, environment protection and operator responsibilities.
