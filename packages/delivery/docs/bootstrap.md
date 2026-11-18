# Operator-owned Azure bootstrap

This opt-in script is **not** `task bootstrap`. That existing task owns local
dependencies and Git hooks, not Azure. Nothing here installs tools, logs in,
changes Git, switches the global Azure context, or configures a CI host.

The default is deterministic JSON printed to stdout, with **zero subprocesses**,
including Azure, Git, login and executable discovery. It does not read a cloud
account, environment defaults or remote state. A plan is not an Azure what-if,
authorization check, region availability check or proof of OIDC claims.

## Command and operator inputs

Run the standalone script with an already installed Python 3.13 or 3.14.
No toolkit installation is needed. All values below are deliberately examples;
replace them with independently reviewed project values before applying.

```powershell
python packages/delivery/scripts/bootstrap_azure.py `
  --tenant-id 00000000-0000-0000-0000-000000000000 `
  --subscription-id 11111111-1111-1111-1111-111111111111 `
  --resource-group example-rg `
  --location westeurope `
  --identity-name example-ci `
  --ci-host github `
  --issuer https://token.actions.githubusercontent.com `
  --subject repo:example/repository:environment:dev `
  --audience api://AzureADTokenExchange `
  --oidc-reviewed
```

Required arguments:

| Argument | Operator decision |
| --- | --- |
| `--tenant-id`, `--subscription-id` | Explicit canonical UUIDs, never names or inferred account defaults. |
| `--resource-group`, `--identity-name` | Dedicated project names: 2–63 lowercase ASCII letters, digits or hyphens, beginning with a letter. |
| `--location` | Explicit public Azure region code, not a display name. Availability is checked by Azure only during apply. |
| `--ci-host` | `github` or `ado`; no guessed host. |
| `--issuer`, `--subject`, `--audience` | Exact verified claims for the selected CI host and trust boundary. These are nonsecret identifiers. Repeat `--subject` once per trusted subject of **one** environment, for example a legacy and a migrated service connection subject: 1–20 distinct values, one federated credential each. Never trust several environments with one identity; see [Remaining risks](#remaining-risks). With `--ci-host github --access deploy`, every subject must be `repo:<owner>/<repo>:environment:<name>` for the same environment; see [GitHub](#github). |
| `--oidc-reviewed` | Attestation that an operator verified those claims and reviewed the actors able to obtain them. The script does not verify tokens or fetch discovery documents. |
| `--apply` | Optional, explicit permission to perform only the bounded actions below. Omit for an offline plan. |

Optional `--access {read,deploy}` (default `read`) selects the resource-group
grant; see [Access levels](#access-levels). Omitting it, or passing
`--access read`, produces exactly the same plan as before the option existed.
Optional `--emit {github,azure-devops}` additionally prints CI-host setup
commands; see [Printed CI-host setup](#printed-ci-host-setup).

### Federated credentials

The script creates one federated credential per `--subject`, all with the same
issuer and audience. Microsoft Entra allows at most 20 per identity, so the
script accepts 1–20 subjects and refuses duplicates.

| Subjects | Credential names |
| --- | --- |
| One | `ci` |
| Several | `ci-<12 hex>`, derived deterministically from each subject |

An existing credential is matched by subject. One named `ci` is reused even when
you add subjects later, and only the missing subjects are created. See
[Reentry, ownership and errors](#reentry-ownership-and-errors) for what is refused.

Neither secrets nor Teams URLs belong in these flags. No environment variable,
current subscription or logged-in principal supplies a missing argument. The
script rejects shell metacharacters, wildcards, credentials/query strings in
issuers and recognizable synthetic apply targets. Synthetic detection is a
guardrail, not proof that arbitrary plausible identifiers are real or authorized.

### GitHub

Only the public GitHub Actions issuer is supported. Subjects may select a
specific environment, branch or tag using GitHub's documented `repo:...` shape.
The audience must be `api://AzureADTokenExchange`. Encoded subjects (`%`),
customized claim templates, pull-request subjects and GitHub Enterprise Server
issuers are deliberately unsupported; stop rather than weakening a trust to fit.

With `--access deploy`, the script accepts only
`repo:<owner>/<repo>:environment:<name>` subjects, all for one repository
environment; it compares owner, repository and environment names
case-insensitively, as GitHub does. A branch or tag subject would let any
workflow run on that ref obtain the deploy token without the environment's
reviewers or branch policy, and a second environment's subject would let that
environment's approvals reach this one. Bootstrap one deploy identity per
environment. Branch and tag subjects remain available with `--access read`.

An environment name in a subject **does not mean the environment is protected**.
The repository owner must choose allowed branches/tags, reviewers and deployment
actors, review who can edit workflows or environments, and configure the required
protection rules. Account for repository-plan feature availability. For a
protected environment, the [deploy workflow](deploy.md#jobs) fails unless
*Prevent self-review* is on, administrator bypass is off and deployment branches
are restricted; never silently auto-approve.
The bootstrap never calls `gh` and never creates environments or repository
secrets; `--emit github` only prints commands for review.
Tenant ID, subscription ID and the resulting client ID are nonsecret CI settings;
the workload obtains short-lived tokens using the CI host's native OIDC flow.

### Azure DevOps

Copy the issuer and subject **from the intended service connection's manual
workload identity configuration**; never derive them from organization display
names or assume that a newly generated connection uses the legacy subject.
The supported Entra issuer is
`https://login.microsoftonline.com/TENANT_UUID/v2.0`, matching the explicit tenant.
Generated `/eid1/...` subjects and legacy `sc://organization/project/connection`
subjects are accepted within a conservative ASCII syntax.

Existing legacy `https://vstoken.dev.azure.com/ORGANIZATION_UUID` issuers are
accepted only with a `sc://...` subject. Microsoft's current documentation marks
the legacy issuer deprecated, retiring July 1, 2027 for eligible public-cloud
connections. Follow the service connection's conversion guidance; this script
will **not overwrite** an old credential with new claims. A separately reviewed
trust migration must precede reuse.

Use the resulting client ID for the reviewed user-assigned managed identity.
The project/service-connection owner must choose authorized pipelines, service
connection administrators, environment approvers and checks. Do not select
“grant access permission to all pipelines” by default. Saving/verifying a service
connection and any approvals remain manual operator actions.

The connection's Entra issuer and subject exist only after the connection is
created. With `--emit azure-devops`, create the service connection from the
printed commands first, copy its generated subject, and then rerun the bootstrap
with that exact `--subject` before the connection is first used.

## Printed CI-host setup

`--emit github` (with `--ci-host github`) or `--emit azure-devops` (with
`--ci-host ado`) adds an `emit` object to the JSON output. It holds commands,
notes and, for Azure DevOps, request bodies. They are **printed for review only
and never run**, in plan or apply mode. Before apply, the client ID is the
placeholder `CLIENT_ID_FROM_IDENTITY`; after apply, it is the identity's client
ID. Verify each command against the current CLI or REST reference and run it
yourself as an authorized operator.

| Flag | Meaning |
| --- | --- |
| `--deploy-branch` | Branch name allowed to deploy in the printed commands; default `main` |
| `--ado-organization` | `https://dev.azure.com/<organization>` URL; required for `azure-devops` |
| `--ado-project`, `--ado-environment` | Project and pipeline environment names; required for `azure-devops` |
| `--ado-service-connection` | Service connection name; defaults to `--identity-name` |

The `--ado-*` flags are refused without `--emit azure-devops`, and `--emit` must
match `--ci-host`.

**GitHub.** For each `repo:...:environment:<name>` subject, the output has
`gh` commands that:

- set the environment's deployment branch policy to custom branches and add
  `--deploy-branch`;
- set `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID` as
  environment variables.

Branch and tag subjects, accepted only with `--access read`, get no commands. The
environment `PUT` replaces existing protection settings, so merge it with existing
reviewers. Required reviewers with *Prevent self-review*, clearing *Allow
administrators to bypass configured protection rules* (the printed `PUT` does not
set it) and the Terraform state variables stay separate operator steps.

**Azure DevOps.** The output has `az devops` and `az repos` commands plus the
request bodies `service-connection.json`, `environment.json` and
`branch-control.json`. They:

1. look up the project ID;
2. create a manual workload identity federation service connection, not shared
   with other projects;
3. create the pipeline environment;
4. add a *Branch control* check on that environment that allows only
   `refs/heads/<deploy-branch>` and requires the branch to be protected;
5. add a minimum-approver policy (one approver, creator's vote not counted) on
   `--deploy-branch` in the repository.

Replace the `PROJECT_ID_FROM_ADO`, `ENVIRONMENT_ID_FROM_CREATE` and
`REPOSITORY_ID_FROM_ADO` placeholders with IDs returned by the earlier commands.
The Branch control check is posted with `az devops invoke` to a preview API
version (`7.1-preview.1`). **Check its check type and definition IDs, and every
request body, against the current
[Azure DevOps REST reference](https://learn.microsoft.com/en-us/rest/api/azure/devops/)
before running them.** The printed Branch control check targets the environment
only. In the UI, add *Approvals*, *Exclusive lock* and *Required template* to the
environment, and *Branch control* and *Required template* to the service
connection; allow only the pinned toolkit templates. Authorize the connection per
pipeline; see [deploy](deploy.md#azure-devops).

## Explicit apply contract

Use the **same reviewed arguments plus `--apply`**, from an operator-controlled
session with an already installed, reviewed Azure CLI. Authentication is a
separate operator action. This script never runs `az login`, `az account set`,
`az cloud set`, Graph commands, package installers or extension installers.
The inherited Azure CLI configuration remains operator-owned.

Before any mutation:

1. `az account show --subscription SUBSCRIPTION_UUID` must return the expected
   tenant, subscription, `Enabled` state and `AzureCloud` environment.
2. `az cloud show` must confirm the active public-cloud ARM and Entra endpoints.
   This unscoped CLI command has no subscription option. Every subscription-scoped
   read and write explicitly passes `--subscription`; no global context changes.
3. Inspect the resource group, managed identity, **all** identity credentials and
   relevant role assignments. Read failures are not treated as absence.
   Assignment inspection uses `--fill-principal-name false` and does not resolve
   a signed-in user or principal through Graph.

Only missing resources are created using native commands:

| Resource | Command family and boundary |
| --- | --- |
| Resource group | `az group create`, at the explicit subscription and location. |
| User-assigned managed identity | `az identity create`, inside that group. |
| Federated credential per `--subject` | `az identity federated-credential create`, exact issuer/subject/audience, no claim wildcard; only for subjects not already trusted. |
| Reader role assignment (default `--access read`) | `az role assignment create`, that identity's **principal/object ID**, `ServicePrincipal` type, selected resource group scope only. |
| Contributor and constrained RBAC administrator (`--access deploy`, instead of Reader) | Two `az role assignment create` calls with the same identity, type and scope; the second adds `--condition ... --condition-version 2.0`. |

### Access levels

**`read` (default).** Reader's pinned built-in role ID is
`acdd72a7-3385-48ef-bd42-f606fba81ae7`. It deliberately **cannot deploy workloads**,
write state blobs, assign roles or administer the tenant. Choose separate
workload-specific permissions after reviewing the deployment resources and
actions. With `read`, the bootstrap does not grant Contributor, Owner, User
Access Administrator or Role Based Access Control Administrator.

**`deploy`.** Replaces Reader with exactly two assignments at the selected
resource group, both for the identity's principal ID as `ServicePrincipal`:

| Role | Pinned ID | Condition |
| --- | --- | --- |
| Contributor | `b24988ac-6180-42a0-ab88-20f7382dd24c` | None. |
| Role Based Access Control Administrator | `f58310d9-a9f6-439a-9e8d-f62e7b41a168` | Version 2.0, Microsoft's documented [constrain roles and principal types](https://learn.microsoft.com/en-us/azure/role-based-access-control/delegate-role-assignments-examples) example. |

Contributor lets the pipeline deploy the delivery templates into this group
but cannot write role assignments. The templates also assign data-plane roles
to their own workload identities, which needs `roleAssignments/write`. Owner or
unconstrained User Access Administrator would also let the pipeline grant
itself or any user full control. The condition therefore allows
`roleAssignments/write` and `roleAssignments/delete` **only** when the role is
one of `DELEGABLE_ROLES` in `bootstrap_azure.py`, and only when the principal
type is `ServicePrincipal`. The CI identity therefore **cannot** assign Owner,
User Access Administrator, Role Based Access Control Administrator, Contributor
or any role outside that list, and cannot target users or groups. All other
writes stay inside the resource group. `DELEGABLE_ROLES` is the single source of
truth for that list, kept in step with the delivery infrastructure templates:

| Role definition ID | Built-in role |
| --- | --- |
| `5e0bd9bd-7b93-4f28-af87-19fc36ad61bd` | Cognitive Services OpenAI User |
| `53ca6127-db72-4b80-b1b0-d745d6d5456d` | Foundry User (formerly Azure AI User) |
| `1407120a-92aa-4202-b7e9-c0e197c71c8f` | Search Index Data Reader |
| `8ebe5a00-799e-43f5-93ac-243d3dce84a7` | Search Index Data Contributor |
| `3913510d-42f4-4e42-8a64-420c390055eb` | Monitoring Metrics Publisher |
| `7f951dda-4ed3-4680-a7ca-43fe172d538d` | AcrPull |
| `8311e382-0749-4cb8-b61a-304f252e45ec` | AcrPush |
| `a97b65f3-24c7-4388-baec-2e87135dc908` | Cognitive Services User |
| `4633458b-17de-408a-b874-0445c86b69e6` | Key Vault Secrets User |
| `ba92f5b4-2d11-453d-a403-e96b0029c9fe` | Storage Blob Data Contributor |

The plan JSON shows `access`, both assignment names, role names, role definition
IDs, scope, principal type and the exact condition string. Review them before
applying, together with the [remaining risks](#remaining-risks) and
[deletion locks](#deletion-locks).

Terraform remote state still needs the
[terraform-state](../infra/terraform-state/README.md) module's
**container-scope** Storage Blob Data Contributor assignment. A blob role at the
resource group is not the intended state boundary. Platform teams that do not
allow a pipeline to hold an RBAC administration role can **pre-assign equivalent
roles** themselves, such as Contributor plus their own reviewed role assignments
for the template identities. They then use the default `read` instead of
`deploy`.

Switching levels never deletes anything. A `read` → `deploy` rerun refuses the
existing Reader assignment, and a `deploy` → `read` rerun refuses the existing
Contributor/RBAC assignments. An authorized operator must review and remove the
old assignments separately, and only then rerun.

The caller needs authorized group/identity/federated-credential write permissions
and permission to create the specific role assignments. With `deploy`, that
means authority to assign Contributor and a conditioned Role Based Access
Control Administrator at the group (typically Owner or User Access
Administrator there). The new CI identity is
not the operator. If the caller lacks permissions, stop and ask an appropriately
authorized operator to perform the reviewed operation; do not escalate the caller
or CI principal automatically. No provider registration or privilege acquisition
is implemented.

### Deletion locks

Neither `deploy` role can write a
[management lock](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/lock-resources):
Contributor excludes `Microsoft.Authorization/*/Write`, and the constrained RBAC
administrator writes only role assignments. Templates that create `CanNotDelete`
locks, such as the starter in `staging` and `prod` and the compositions in
`prod`, would fail the first prod-like deploy with `AuthorizationFailed`.

Before that deploy, an operator with Owner or User Access Administrator creates
and assigns a custom role at the same resource group. The bootstrap never creates
it. It reads and writes locks but cannot delete them, so CI cannot remove
deletion protection:

```json
{
  "Name": "<project> lock writer",
  "IsCustom": true,
  "Description": "Read and create management locks; cannot delete them.",
  "Actions": [
    "Microsoft.Authorization/locks/read",
    "Microsoft.Authorization/locks/write"
  ],
  "NotActions": [],
  "DataActions": [],
  "NotDataActions": [],
  "AssignableScopes": ["/subscriptions/<subscription-id>/resourceGroups/<resource-group>"]
}
```

```powershell
az role definition create --role-definition '@lock-writer.json'
az role assignment create `
  --assignee-object-id <principal-id> `
  --assignee-principal-type ServicePrincipal `
  --role "<project> lock writer" `
  --scope /subscriptions/<subscription-id>/resourceGroups/<resource-group>
```

- Use the identity's principal ID, not its client ID, and one role per
  environment's resource group.
- Without `locks/delete`, a Terraform destroy or replacement of a lock, or turning
  deletion protection off, fails in CI. An operator removes the lock first.
- `locks/write` can still change an existing lock's level or notes.
- Bootstrap inspection accepts only the grants of the selected `--access`, so a
  later `--apply` for this identity stops with *Additional identity role
  assignments need review*. Finish reentry, such as adding a subject, first.

### Remaining risks

`deploy` leaves these risks for the operator and platform team:

- **Contributor in the group.** It can modify or delete any unlocked resource in
  the group. Keep the group dedicated to this workload.
- **Self-federation.** The identity lives in the group where it holds
  Contributor, so it can write its own
  `Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials`
  and trust another issuer or subject. Mitigate by creating the identity in a
  separate identity resource group where CI has no role (a platform-team step;
  this script uses one group), or by replacing Contributor with a custom role that
  adds `NotActions`
  `Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials/*`.
  `NotActions` is not a deny, so no other grant may allow it. Also audit or deny
  the operation with Azure Policy, or raise an Activity Log alert on
  `federatedIdentityCredentials/write`.
- **Self-delegation.** The RBAC administrator condition limits the role and the
  principal type, not the principal. The CI identity can grant itself, or a
  service principal it controls, any `DELEGABLE_ROLES` role in the group, such as
  Key Vault Secrets User or Storage Blob Data Contributor. The condition does not
  exclude the identity's own principal ID because the starter grants its deploy
  identity AcrPush on the registry it creates, and an exclusion would deny that
  assignment. Where self-delegation matters, pre-assign the template roles and
  use `read`. Alert on `roleAssignments/write`.
- **Service-native grants and keys.** Contributor can create Cosmos DB SQL role
  assignments and Managed Redis access-policy assignments for any principal, and
  can re-enable local authentication, shared keys or the registry admin user and
  list the keys. Role conditions do not cover these. Assign the deny policies in
  [deploy identity limits](identity-and-network.md#deploy-identity-limits) at
  subscription or management-group scope, where Contributor on the group cannot
  change or exempt them.
- **Shared identity.** Use one CI identity per environment. Never let one
  identity trust the subjects of several environments: the least protected
  environment's approvals would then reach every target. For GitHub,
  `--access deploy` refuses subjects of more than one environment. Azure DevOps subjects
  name service connections, not environments, so the script cannot check them;
  give each environment its own service connection and identity.
- **Application authorization.** Container Apps built-in authentication, as the
  compositions configure it, sets no authorization policy (allowed client
  applications or principals), so it accepts any valid token issued for an
  allowed audience. The starter's Entra bearer guard enforces audience and scopes
  or roles in the app. Other apps must authorize in code or at a gateway; see
  [Container Apps authentication](../infra/container-apps/REFERENCE.md).

### Reentry, ownership and errors

Names, ARM IDs, ownership tags and the per-role assignment UUIDs are deterministic.
The `agent-kit-bootstrap` tag on both group and identity encodes the selected
tenant and identity ARM ID. The tag is an ownership convention, **not an
authorization boundary**. Existing resources must already have the exact marker,
location and IDs; this tool does not adopt/retag arbitrary existing resources.
Do not add the marker to bypass a refusal. Existing identity tenant and output
UUIDs must also be valid.

An existing credential must carry one of the reviewed subjects, an accepted name
(`ci` or that subject's derived name) and every other reviewed field. Credentials
for other subjects, changed trust, duplicates, conflicting role
names/principals/scopes/conditions or additional visible grants for this
identity stop apply before any mutation. Only the exact
assignment set for the selected `--access` level is accepted. Any other role,
including a leftover from the other level, is refused and never deleted. The
RBAC administrator condition must equal the reviewed text. The one tolerance:
whitespace outside single-quoted literals is ignored, in case Azure reformats
the expression. Role GUIDs, operators, attribute names and quoted values must
still match exactly, and the condition version must be `2.0`. Role inspection
includes the selected scope and its ancestors, not a tenant-wide access audit.
The dedicated identity must not be shared with unrelated automation. Matching
resources are reused without a write; a partial run can resume.

**Serialize operators for the same target.** Native CLI create operations are
not transactional and some use ARM PUT. Inspection is not an atomic
compare-and-create; a concurrent writer can invalidate the inventory. This is
not a reconciliation controller or safe concurrent-adoption mechanism.

Nonzero CLI exits, unavailable executables, timeouts, malformed JSON and unexpected
responses fail explicitly. No automatic retries, deletes or rollback are hidden.
Raw CLI stdout/stderr are withheld on failure to avoid echoing credentials.
Successful output contains selected nonsecret IDs and next steps, never tokens,
keys or secrets. Partial resources can remain after a timeout or denied role
write; inspect with an authorized operator before retrying.

The offline plan includes the exact native argument vectors: group, identity,
one credential per subject, and one role for `read` or two for `deploy` (four
and five with a single subject). Each role vector contains the explicit
`PRINCIPAL_ID_FROM_IDENTITY` placeholder. If a separate
authorized actor must create the roles, replace **only that placeholder** with the
verified identity `principalId`, review the scope, roles, condition and assignment
UUIDs, and execute them separately. The client ID is not a principal ID. Rerunning
apply will inspect and reuse those matching assignments.

## Optional state backend: use the canonical module

This bootstrap does not duplicate or deploy state storage. Reuse **one**
implementation and the complete
[terraform-state bootstrap procedure](../infra/terraform-state/README.md#bootstrap-order)
in a separate approved operator operation. It owns storage, container-scoped
RBAC, firewall/private-endpoint requirements, recovery controls and migration;
Bicep needs no local state. Never apply both implementations over one backend or
substitute local state in CI. The backend cannot provision itself during init.

## Teams and tenant consent

There is deliberately no Teams destination or webhook flag. The caller chooses
the team/channel and the authorized notification actor in the relevant native
workflow or operator-owned configuration. Public team/channel identifiers are
not secrets, but webhook URLs, tokens and credentials must use the CI host's
approved secret mechanism, not flags, committed configuration or plan output.
Tenant-controlled OAuth/application consent belongs to the tenant's authorized
administrator; this bootstrap requests no consent and grants no Graph roles.

## Offline verification

The focused tests use injected fake JSON/process responses,
never installed Azure/`gh`/Git executables, cloud accounts or credentials.

Run from the checkout using the already provisioned environment:

```powershell
uv run --locked --no-sync python -m pytest tests/integration/delivery/test_azure_bootstrap.py -q -p no:cacheprovider
task verify
```

These are offline behavior/schema and policy checks, not live Azure
certification. The focused tests cover conflicting role grants, failed creation,
malformed responses and sanitized CLI failures. Repository verification also
enforces dependency policy; see the unresolved
[development-tool license decision](https://github.com/lfr-ai/agent-kit/blob/main/docs/dependency-security.md#copier-development-tool).

From the toolkit checkout, `task bootstrap:azure -- <arguments>` invokes the
same script using the already provisioned environment. It does not depend on
local `bootstrap`, add `--apply`, infer targets, authenticate or install
dependencies. Ordinary `task bootstrap` remains local-only. A relocated consumer
can invoke the standalone Python script directly without the toolkit Taskfile.

## Rollback and risks

Before apply, no cloud or state was touched. After an operator applies, a source revert does
**not** undo resource groups, identities, federation, role assignments, audit
events or state. Review the deterministic IDs and current ownership before any
separate teardown. Remove the CI trust and role assignments first if revoking access,
then decide whether the dedicated identity can be removed. Never blindly delete
the resource group: it may now contain workloads or state.

State blobs, their versions, local-state migrations and production deletion locks
need the canonical module's recovery/retention procedure. Deleted identity
principal/client IDs cannot be restored by rerunning this script; recreating an
identity may require a separately reviewed role assignment replacement. Do not
silently overwrite that conflict.

## Official grounding

Consulted during implementation; native service behavior still requires operator
verification in the intended environment:

- [Azure account show](https://learn.microsoft.com/en-us/cli/azure/account#az-account-show)
- [Azure cloud show](https://learn.microsoft.com/en-us/cli/azure/cloud#az-cloud-show)
- [Managed identities](https://learn.microsoft.com/en-us/cli/azure/identity)
- [Federated credentials](https://learn.microsoft.com/en-us/cli/azure/identity/federated-credential)
- [Role assignment CLI and avoiding Graph lookup](https://learn.microsoft.com/en-us/cli/azure/role/assignment)
- [Delegate role assignments with conditions: constrain roles and principal types](https://learn.microsoft.com/en-us/azure/role-based-access-control/delegate-role-assignments-examples)
- [GitHub OIDC claims](https://docs.github.com/en/actions/reference/security/oidc)
- [Azure DevOps manual workload identity and issuer migration](https://learn.microsoft.com/en-us/azure/devops/pipelines/release/configure-workload-identity)
