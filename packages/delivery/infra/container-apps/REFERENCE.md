# Container Apps: operator gates, validation and sources

Start with the [consumer contract](README.md).

Environment/secret behavior follows the official
[environment variable contract](https://learn.microsoft.com/en-us/azure/container-apps/environment-variables)
and [Key Vault reference contract](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets).

## External access and defaults

An omitted (null) identity input creates `${appName}-identity`. **ACR, Key Vault or
Application Insights access requires an existing, pre-authorized user-assigned
identity**; this composition does not change external RBAC, vaults, registries
or monitoring resources. Supply the ACR login server
and an image from that same server. Use managed identity only, never registry
passwords. The operator grants `AcrPull` for RBAC registries (or the appropriate
repository-reader role/condition for ABAC registries), enables ARM-audience
tokens, grants Key Vault Secrets User, grants `Monitoring Metrics Publisher`
(the [application-insights](../application-insights/README.md) composition
does this), and verifies propagation/network access *before* deploying.
Existing identities are neither owned nor locked here.

The [Azure bootstrap](../../docs/bootstrap.md) can establish a reviewed CI identity,
but grants only Reader. Workload deployment, managed identity assignment, Insights
role assignment, state storage and runtime Key Vault access need separate,
explicitly scoped operator grants. Reader is insufficient for each of those writes
and for secret-value access; do not silently broaden it.

The app gets 0.5 CPU / 1 GiB unless `cpu`/`memory` select another Consumption
pair, single-revision traffic, HTTP concurrency scaling
at 100, external HTTPS ingress with insecure ingress disabled (public unless a
private endpoint is set). TLS terminates at
ingress; startup/liveness use `/health/live`, readiness uses `/health/ready`
over HTTP inside the environment. Startup allows about five minutes. The
consumer image must listen on `0.0.0.0:targetPort` and implement these endpoints.
Outputs are resource IDs, the HTTPS URL and the environment default domain, not
keys or secret values.

## Private endpoint and public exposure

`privateEndpoint` adds `${environmentName}-pe` in `subnetId` with group
`managedEnvironments`, a `default` DNS zone group in `privateDnsZoneId`, and
`publicNetworkAccess: Disabled` on the environment. Without it the module does
not set `publicNetworkAccess`, so Azure keeps its default (`Enabled`).
Staging and production reject a missing endpoint unless the environment is
internal: direct public ingress is not allowed there, so staging rehearses the
production topology. The guard checks the ID shapes and that the zone is
`privatelink.<location>.azurecontainerapps.io` for the module's region, not
that the resources exist.

**Why the environment stays external.** Microsoft's networking guide allows
`Enabled` or `Disabled` public network access with an external virtual IP and
only `Disabled` with an internal one. Private endpoints need `Disabled`, and
both private endpoint tutorials use an external environment without its own
virtual network and external app ingress. Internal mode needs an
infrastructure subnet and is fixed at creation, so switching would replace the
environment. The module therefore keeps `internal: false` and app ingress
`external: true`; with access `Disabled`, "external" means reachable only
through private endpoints. Private endpoints also need a workload-profiles
environment, which this module always creates. An infrastructure subnet is not
needed for the endpoint, so `dev`/`test` may add an endpoint without VNet
integration.

Network prerequisites stay operator-owned:

- The endpoint subnet's virtual network must be in `location`. Use a subnet
  separate from the delegated infrastructure subnet.
- Link the zone to every virtual network whose clients resolve the app,
  including the hub that serves on-premises DNS forwarding. The zone group
  writes an A record named after the first label of `environmentDefaultDomain`.
  Without a link, clients resolve the public name and are refused.
- Network security groups, routes and DNS forwarding are not created here.
- The module's own endpoint is approved automatically only when the deploying
  identity may approve connections on the environment. Otherwise it stays
  **Pending**; approve it as below.

**Public exposure (operator-owned).** Staging and production are private, and
this repo ships no edge, WAF or global-routing module. For public exposure the
operator adds an edge WAF or gateway outside this kit, for example Azure Front
Door Premium with Private Link to this environment (group `managedEnvironments`,
this `location`), or Application Gateway or API Management. A Private Link
origin requests a private endpoint connection on the environment, and no
traffic flows until it is approved. Public access is already disabled here.
Deleting repository sources never destroys deployed resources.

Approval is a reviewed operator step. Never run it from the pipeline or with
ambient credentials; use a scoped identity approved for this change.

1. List the connections on the environment:

   ```shell
   az network private-endpoint-connection list --name <environment-name> --resource-group <resource-group> --type Microsoft.App/managedEnvironments
   ```

2. Pick each **Pending** connection whose
   `properties.privateLinkServiceConnectionState.description` identifies the
   edge you are onboarding. Its ID
   ends in `/managedEnvironments/<environment-name>/privateEndpointConnections/<connection>`.
   It is not the private endpoint ID under `Microsoft.Network/privateEndpoints`.
   An edge may create several requests; approve every matching one.
3. Approve each one:

   ```shell
   az network private-endpoint-connection approve --id <connection-id> --description "Approved for <edge name>, change <change-id>"
   ```

4. Check that the edge endpoint serves the app and that the app URL is
   refused from the internet. Reject unknown requests with
   `az network private-endpoint-connection reject --id <connection-id>`.

Private Link reaches Container Apps only in supported regions and
only over HTTP(S); TCP is not supported through private endpoints.

**Internal environment DNS and extra VNets.** The default-domain zone is
linked to the infrastructure VNet. `linkedVirtualNetworkIds` adds links for a
hub or peered spokes; peering and on-premises DNS forwarding stay operator-owned,
and a VNet can link to only one zone with the same name. Link names are
`<environmentName>-<guid(lowercase VNet ID)>` in Bicep and the identical RFC 4122
UUIDv5 (`uuidv5`, namespace `11fb06fb-712d-4ddd-98c7-e71bbd588830`) in
Terraform, so both tools produce the same names; the tests prove the Bicep
`guid()` value offline. The zone lock is named `foundation-protection` like the
other module locks; an existing zone lock named `deletion-protection` from an
earlier revision is not renamed by Bicep incremental deployments (see
[rollback](#rollback)).

**`publicNetworkAccess` semantics.** An internal VIP accepts only `Disabled`, a
private endpoint needs `Disabled`, and an internal environment cannot be
switched to external later. The module therefore forces `Disabled` for both
private topologies and rejects an explicit `Enabled` with either, offline in both
languages, rather than sending a value the platform rejects or silently
overriding the caller.

## Custom domain and managed certificate

`customDomain` creates `Microsoft.App/managedEnvironments/managedCertificates`
`<appName>-cert` (`domainControlValidation: CNAME`) after the app, and adds the
host name to app ingress (`bindingType` `Disabled`, then `SniEnabled` with the
certificate ID). The app refers to the certificate by a computed ID, not a
symbolic reference, so there is no dependency cycle between the app and the
certificate. Managed certificates are free, renew automatically and need:

- a publicly reachable app, so the module rejects internal environments, private
  endpoints and `publicNetworkAccess: Disabled`. Whether Microsoft issues managed
  certificates behind those topologies is not verified here, so the combination
  is gated rather than attempted; use an operator-owned edge with its own TLS for private apps;
- the CNAME to the app FQDN and the `asuid.<host>` TXT record with the
  environment's `customDomainVerificationId` **before** the host name is added;
- CAA records, if present, that allow `digicert.com`;
- a subdomain; apex domains need an A record and HTTP validation, which this
  module does not implement.

The verification ID is a public DNS value, not a secret; Terraform exports only
that property. DNS records are operator-owned (often another subscription or
provider) and never created here.

## Entra authentication

`authentication` adds `Microsoft.App/containerApps/authConfigs` named
`current` with the platform enabled, `globalValidation` and only the
`azureActiveDirectory` provider. API mode returns `401` for requests without a
valid bearer token; `signIn` redirects browsers to Entra instead. With
`publicHostName`, `httpSettings.forwardProxy.convention: Standard` makes the
platform build redirect URLs from the standard forwarded-host headers, so sign-in through
an operator-owned edge returns to the public host, and `authCallbackUrl` uses that host.
The issuer and guards are Azure public cloud only, like the Key Vault guard.

**Why no managed-identity federated credential.** Microsoft documents the
secretless `OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID` pattern for App Service and
Azure Functions only, as an app setting named in `clientSecretSettingName`.
The Container Apps Entra guide does not document it; there,
`clientSecretSettingName` names a Container Apps secret, and secret names allow
only lowercase letters, digits and hyphens. Instead the module leaves the
client secret unset. The Container Apps guide documents that implicit flow is
then used and only an ID token is returned, which needs **ID tokens** enabled
on the app registration. No secret exists to leak, rotate or expire. Microsoft
discourages implicit grant where other flows are viable. Here it only signs
users in; the app cannot get access or refresh tokens for downstream APIs from
the token store. Revisit when Container Apps documents a managed-identity
client assertion. Operators must not add a client secret outside this source.

Operator steps stay outside the pipeline and need Entra application write
access, not the deployment identity's Azure RBAC:

1. Use an existing app registration (single tenant recommended). For API mode
   set an application ID URI, such as `api://<clientId>`, and pass it in
   `allowedAudiences` if clients request tokens for it.
2. With `signIn`, after deployment register the redirect URI and enable ID
   tokens (the list is replaced; include existing URIs):

   ```shell
   az ad app update --id <clientId> --web-redirect-uris <authCallbackUrl> --enable-id-token-issuance true
   ```

3. Check that an unauthenticated request gets `401` (API mode) or a redirect
   to `login.microsoftonline.com` (sign-in), and that sign-in returns to the
   public host.

Built-in authentication only authenticates. Express authorization through app
roles or group claims on the registration and enforce it in the application,
using the token claims or the `X-MS-CLIENT-PRINCIPAL-*` headers that the
platform injects. Health probes run inside the environment and are not affected.
A public health URL, such as the deploy pipeline's health check, must be listed
in `excludedPaths` (`globalValidation.excludedPaths`); keep that list to
unauthenticated, non-sensitive endpoints.

## Operator gates and ownership

- Zone-enabled regions need an existing same-region, dedicated subnet for
  workload-profile environments (at least `/27`, delegated to
  `Microsoft.App/environments`). Validate address capacity, routing, DNS and
  egress. Zone/subnet/location changes can require environment replacement.
  Two replicas are a floor, not an application SLO or regional disaster recovery.
- Log Analytics retains `logRetentionDays` (default 30, 30–730), disables local key authentication and receives
  console/system logs through Azure Monitor diagnostic settings. No
  `listKeys`, workspace key parameters or Terraform shared-key state.
  Application logs themselves can still leak secrets: consumers own redaction,
  retention/compliance, alerting, budgets and access control.
- Key Vault versionless references allow platform rotation; versioned references
  pin a secret version. Test rotation/revision behavior and vault firewalls in
  the target environment. State still contains IDs/URLs and configuration;
  use the approved encrypted, access-controlled, locked remote backend.
- Production's `CanNotDelete` locks cover app, environment, workspace, any
  created identity and the internal-environment DNS zone; the managed
  certificate is not locked. They do **not** block updates or protect against an actor
  allowed to remove locks. Terraform destroy removes its locks first; these are
  not `prevent_destroy`. Operator policy/approvals must deny unreviewed destroy,
  replacement and lock removal. Bicep incremental deployment does not remove
  old resources/locks simply because declarations or conditions disappear.
- Ingress, public or private, is not authentication, WAF or application
  authorization; custom-domain TLS is only the opt-in managed certificate. The private endpoint limits who can reach the
  environment; zone links, network rules, any edge/WAF and resource-provider
  registration profiles are operator/parent-owned, not implied by this module.
- Caller-owned AzAPI provider configuration should set
  `skip_provider_registration = true` and `enable_preflight = false` for offline
  checks. Authentication/subscription comes from the approved workload identity
  environment, never source. No login, plan against Azure, apply or deploy is
  part of the offline checks.

No `azure.yaml` is supplied. An `azd up` service would also build/deploy an app
and could overwrite the digest-managed revision. No second composition or
unsupported claim of azd lifecycle ownership is provided.

## Telemetry routing

The telemetry inputs only add environment variables (see the
[README](README.md#telemetry-opt-in)); the app's own OpenTelemetry SDK exports.
Omitting both inputs keeps the container `env` value unchanged, so
upgrading this composition does not create a new revision. Setting or changing
them creates one, like any configuration change.

Nonsecret `environmentVariables` and Key Vault `secretReferences` are merged with
these module-owned variables, not used to override them. All six telemetry names
are reserved even before enabling export. This deliberately tightens validation
for callers that previously used a telemetry name as a secret destination while
telemetry was disabled; migrate to the module's telemetry inputs before upgrading.
The credential-override names `AZURE_CLIENT_SECRET`,
`AZURE_CLIENT_CERTIFICATE_PATH` and `AZURE_FEDERATED_TOKEN_FILE` are reserved as
well: `DefaultAzureCredential` tries the environment credential before managed
identity, so either input could otherwise swap the app off its managed identity.
Plain map entries and secret-reference destinations cannot collide, including
case variants within either input or across both. Reserved-name and
credential-slot checks also ignore case; accepted names retain their casing.
This rejects ambiguities in applications with case-insensitive settings without
rejecting single lowercase nonsecret names. The new
empty map default preserves the old empty/default container environment.
Azure otherwise uses the last occurrence of a duplicate environment name; this
module rejects that ambiguity.

- **Application Insights**: the connection string identifies the resource and
  is not a credential; ingestion in test and prod is authenticated with an
  Entra ID token for the identity named by `AZURE_CLIENT_ID`. For the Azure
  Monitor OpenTelemetry distro, pass
  `ManagedIdentityCredential(client_id=os.environ["AZURE_CLIENT_ID"])` (or
  `DefaultAzureCredential`, which reads the same variable) as `credential`. Bicep
  reads the client ID with `reference()` at deployment time; Terraform reads it
  with an `azapi_resource` data source whenever an existing identity is given,
  so a connection string that is unknown until another module applies does not
  block the plan.
- **OTLP** (for example Langfuse): `OTEL_EXPORTER_OTLP_ENDPOINT` is the base URL;
  SDKs append `/v1/traces`. The header string, for Langfuse
  `Authorization=Basic <base64 public-key:secret-key>,x-langfuse-ingestion-version=4`,
  is a credential: store it in Key Vault and reference it through
  `secretReferences` as `OTEL_EXPORTER_OTLP_HEADERS`. Langfuse ingests traces
  only, so export only traces over OTLP when it is the endpoint.
- **Both**: the application must deliberately configure each exporter. The
  generated starter installs only a trace exporter for Application Insights when
  configured: no SDK log or metric export. Sanitized stdout/stderr
  is collected by Container Apps into Log Analytics, not exported again by the SDK.

**Why not the managed OpenTelemetry agent.** The environment-level
`appInsightsConfiguration`/`openTelemetryConfiguration` agent first appears in
the stable `Microsoft.App` 2026-07-01 API; the 2025-07-01 API used here and the
pinned Bicep 0.39.26 type index do not have it, and Microsoft's examples still
use preview API versions. Independent of API status, its documented
limitations conflict with this toolkit: the Application Insights destination
requires local authentication (test and prod disable it), the agent exports
over gRPC only (Langfuse accepts OTLP over HTTP only), credential headers must
be written into the template because Key Vault is not supported, and it runs as
one non-scalable replica per environment. Revisit when those limitations are
lifted.

## Langfuse

Prefer **Langfuse Cloud** (OTLP endpoint
`https://cloud.langfuse.com/api/public/otel` for the EU region; `us.`, `jp.` or
`hipaa.` before `cloud` for the others) or the **official Azure self-hosting
deployment**. Do not hand-build a Langfuse stack on Container Apps.

Self-hosted Langfuse (current major version v4) runs a web and a worker
container and needs four stateful dependencies: PostgreSQL (transactional
data), ClickHouse (traces, observations and scores), Redis or Valkey (cache
and queue) and S3-compatible or Azure Blob storage (events and attachments).
Langfuse positions Docker Compose for local use and testing only. The official
Azure path is the `langfuse-terraform-azure` module: it deploys AKS with the
Helm chart, Azure Database for PostgreSQL flexible server, Azure Managed Redis,
a storage account, Key Vault and Application Gateway, with ClickHouse in the
cluster. It needs Owner or User Access Administrator on the target scope and a
two-stage apply (cluster first). Running the same dependencies on Container
Apps would leave ClickHouse durability, upgrades, backups and UTC time-zone
requirements to you, without the vendor's tested deployment.

Sources: [OpenTelemetry endpoint](https://langfuse.com/integrations/native/opentelemetry),
[self-hosting overview](https://langfuse.com/self-hosting),
[Azure deployment](https://langfuse.com/self-hosting/deployment/azure),
[Azure Terraform module](https://github.com/langfuse/langfuse-terraform-azure)
and [Kubernetes Helm deployment](https://langfuse.com/self-hosting/deployment/kubernetes-helm).

## Offline checks and pins

Checked tool baseline: **Bicep 0.39.26**, **Terraform 1.11.3**.
Terraform pins **Azure/azapi 2.13.0**; it uses no non-Azure providers.
No external Bicep modules or restore are needed. ARM API versions are explicit
in both sources (the diagnostic-settings API is Microsoft's preview API).

Use the [verification command](README.md#verify-and-adopt) from the repository
root with existing tools only; it includes both native format checks.

The tests ZIP and relocate the exact source closure; run Bicep format, lint,
`build --no-restore --stdout` and `build-params --no-restore --stdout`; exercise
exported production/input guards using Bicep's native parameter evaluator; and
run Terraform `validate -json` / `test -no-color` against the **unchanged
variables.tf alone** for positive/negative inputs without any provider.
Native Bicep guards remain in the deployed template too; normal compilation
alone does not evaluate runtime inputs.

Bicep layout: `main.bicep` keeps the public parameters, resources and outputs;
`common.bicep`, `environment.bicep`, `app.bicep` and `auth.bicep` hold the
exported types and guards. They are compile-time `import` files, not modules,
so the compiled template, deployment graph and what-if output stay a single
deployment, and the parameter contract is unchanged. Bicep cannot re-export
imported symbols, so callers that evaluate guards in `.bicepparam` files import
them from those files (see `bicep/tests/*.bicepparam`).

The shared tests exercise the same valid and malformed Key Vault URLs in both
languages, plus independent secret-name/environment-variable uniqueness,
telemetry input and capacity/production guards. They also retain the output
names and scoped-lock contract. `bicep/tests/prod.bicepparam` builds the
production example through its availability and private endpoint guards. The
Terraform mock tests cover no endpoint by default, the endpoint and DNS zone
group shape with public access disabled, and rejection of production without
an endpoint and of zones for another region or service, staging policy, extra
internal DNS links, compute and retention inputs, both custom-domain phases and
the `publicNetworkAccess` and custom-domain rejections, and the credential-override
reservation (38 mocked runs). Syntax validation is
not a substitute for the operator gates above.

Full Terraform resource validation/mock plans additionally require an
operator-reviewed, checksum-verified **Azure/azapi 2.13.0** filesystem mirror
for the installed OS/architecture. Set process-local
`CONTAINER_APPS_AZAPI_MIRROR` to it. Tests initialize only from that directory:
`terraform init -backend=false -input=false -plugin-dir=<absolute-mirror>`,
then `terraform validate -json` and `terraform test -no-color` on the relocated
composition. Every authored test uses a mocked AzAPI provider and `command =
plan`. **No mirror means a reported skip, not a provider-validation pass.**
Mocks do not certify the ARM API, policies, permissions or resource readiness.

Parent prerequisite: provision the reviewed provider, generate the consumer's
`.terraform.lock.hcl` natively with trusted hashes for target platforms, and
retain that lock with the consumer root before the shared delivery check's
`init -lockfile=readonly`. No fabricated lock, downloaded binary or installer
is supplied here. Catalog, manifests and CI integration remain parent-owned.

## Rollback

Before deployment, revert/remove this directory and its dedicated integration
test; no cloud state has changed. After adoption, revert image/configuration
inputs through the owning IaC tool and review the resulting update. Clearing
the telemetry inputs removes their environment variables in a new revision;
telemetry already exported stays at its destination. Locks may
block replacements; removing them is a separately approved operator action.

For an existing Bicep deployment, inspect the previous compiled identity lock
before upgrading. Bicep 0.39.26 omitted the scope for `scope: identity!`, turning
the intended identity lock into a resource-group lock. The direct resource
reference avoids that compiler behavior; tests require an emitted scope on
every lock. An incremental deployment does not remove a previously deployed
group lock. Its removal requires a separate, reviewed operator action.

Never switch Bicep/Terraform ownership by simply applying the other source:
review import/state migration and existing resource names first. Deleted log
data, identity principals, secret rotation, subnet/environment replacements and
externally changed RBAC cannot be undone by a source revert.

Removing `authentication` deletes `authConfigs/current` in Terraform, but an
incremental Bicep deployment leaves it, still enforcing sign-in; disable it with
`az containerapp auth update --enabled false` as a reviewed step. Redirect URIs and
ID-token settings on the app registration are Entra state outside this source.

Changes from this revision:

- Staging now requires zones, two replicas and a private topology. Existing
  staging deployments that were public must keep the previous source revision
  or migrate deliberately; zone and internal-mode changes replace the environment.
- The internal DNS zone lock was renamed from `deletion-protection` to
  `foundation-protection`. Terraform replaces the lock; Bicep incremental
  deployments add the new lock and leave the old one, which an operator removes
  after review.
- Reverting `cpu`, `memory` or `logRetentionDays` is an in-place update; logs
  older than a shortened retention are deleted and cannot be restored.
- Removing `linkedVirtualNetworkIds` entries deletes the links in Terraform but
  not in Bicep incremental deployments.
- Custom domains: unbind first (`bindCertificate: false`), then remove the
  domain; DNS records and deleted certificates are outside source control.

Private endpoint changes have their own limits:

- Adding `privateEndpoint` to a running environment refuses public clients at
  once. Approve any edge connection and link DNS before switching production traffic.
- Removing it deletes the endpoint and its DNS record in Terraform, but not in
  an incremental Bicep deployment. Neither source sets `publicNetworkAccess`
  back, and whether Azure resets it is not verified. Re-enable public access
  only as a reviewed operator change, and only outside production.
- An approved edge connection belongs to the environment, not to either
  source. Revoke it with `az network private-endpoint-connection reject`. The
  production `CanNotDelete` lock may block deleting connections.

## Verified official sources

Researched 2026-11-05. Latest releases observed were
[Bicep 0.48.1](https://github.com/Azure/bicep/releases/tag/v0.48.1),
[Terraform 1.17.1](https://github.com/hashicorp/terraform/releases/tag/v1.17.1),
[AzureRM 5.12.0](https://github.com/hashicorp/terraform-provider-azurerm/releases/tag/v5.12.0)
and [AzAPI 2.13.0](https://github.com/Azure/terraform-provider-azapi/releases/tag/v2.13.0).
Existing native compilers were retained, not upgraded.

- [Container Apps ARM schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2025-07-01/containerapps)
  and [environment schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2025-07-01/managedenvironments).
- [Workspace schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.operationalinsights/2025-07-01/workspaces),
  [diagnostics schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.insights/2021-05-01-preview/diagnosticsettings),
  [identity schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.managedidentity/2024-11-30/userassignedidentities)
  and [lock schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.authorization/2020-05-01/locks).
- [Reliability and zones](https://learn.microsoft.com/en-us/azure/reliability/reliability-azure-container-apps),
  [subnet requirements](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks),
  [health probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes),
  [logging destinations](https://learn.microsoft.com/en-us/azure/container-apps/log-options),
  [Key Vault references](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
  and [managed-identity image pull](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull).
  [ACR role directory](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-rbac-built-in-roles-directory-reference)
  distinguishes RBAC and ABAC access.
- [Custom domains with managed certificates](https://learn.microsoft.com/en-us/azure/container-apps/custom-domains-managed-certificates),
  [managed certificate schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2025-07-01/managedenvironments/managedcertificates),
  [CPU and memory allocations](https://learn.microsoft.com/en-us/azure/container-apps/containers#allocations),
  [Log Analytics retention](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/data-retention-configure)
  and [networking: virtual IP and public network access](https://learn.microsoft.com/en-us/azure/container-apps/networking).
- [Bicep fail guards](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/bicep-functions-flow-control)
  and [Terraform mock tests](https://developer.hashicorp.com/terraform/language/tests/mocking).
- Telemetry, checked while adding the telemetry inputs:
  [managed OpenTelemetry agent and its limitations](https://learn.microsoft.com/en-us/azure/container-apps/opentelemetry-agents),
  the [stable 2026-07-01 Container Apps REST spec](https://github.com/Azure/azure-rest-api-specs/blob/main/specification/app/resource-manager/Microsoft.App/ContainerApps/stable/2026-07-01/openapi.json)
  (first stable version with `openTelemetryConfiguration`),
  [Entra ID authentication for Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/azure-ad-authentication),
  [connection strings](https://learn.microsoft.com/en-us/azure/azure-monitor/app/connection-strings),
  [OpenTelemetry SDK environment variables](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)
  and [OTLP exporter configuration](https://opentelemetry.io/docs/specs/otel/protocol/exporter/).
- [AzAPI resource schema](https://github.com/Azure/terraform-provider-azapi/blob/v2.13.0/docs/resources/resource.md)
  and [provider settings](https://github.com/Azure/terraform-provider-azapi/blob/v2.13.0/docs/index.md).
- Private access, checked 2026-11-12 while adding `privateEndpoint`:
  [private endpoint tutorial](https://learn.microsoft.com/en-us/azure/container-apps/how-to-use-private-endpoint),
  [Private Link tutorial for an operator-owned edge](https://learn.microsoft.com/en-us/azure/container-apps/how-to-integrate-with-azure-front-door),
  [public network access and virtual IP](https://learn.microsoft.com/en-us/azure/container-apps/networking),
  [private DNS zone names](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns),
  [private endpoint schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2025-01-01/privateendpoints)
  and [DNS zone group schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2025-01-01/privateendpoints/privatednszonegroups).
- Entra authentication, checked 2026-11-12 while adding `authentication`:
  [Container Apps authentication](https://learn.microsoft.com/en-us/azure/container-apps/authentication),
  [Container Apps Microsoft Entra provider](https://learn.microsoft.com/en-us/azure/container-apps/authentication-entra)
  (callback path, issuer, ID tokens and implicit flow without a client secret),
  [authConfigs schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2025-07-01/containerapps/authconfigs),
  [Container Apps secret names](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets),
  the App Service-only
  [managed identity instead of a secret](https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-aad#use-a-managed-identity-instead-of-a-secret)
  and [az ad app update](https://learn.microsoft.com/en-us/cli/azure/ad/app#az-ad-app-update).
- [AVM Terraform 0.9.0](https://registry.terraform.io/modules/Azure/avm-res-app-containerapp/azurerm/0.9.0)
  adds `random` and `modtm`; not needed here.
  [AVM Bicep released tags](https://mcr.microsoft.com/v2/bicep/avm/res/app/container-app/tags/list)
  reached 0.23.0; its wider surface/restoration did not simplify this small
  composition. Native resources share the documented ARM schemas.
