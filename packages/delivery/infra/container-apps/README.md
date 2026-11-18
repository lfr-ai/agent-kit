# Azure Container Apps foundation

One app, one managed environment, Log Analytics and managed identity.
No business code, image build or unused backing services. Choose **one**
canonical implementation: [Bicep](bicep/main.bicep) **or**
[Terraform](terraform/main.tf), never both over the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Reference `bicep/main.bicep` as a
resource-group-scoped module or `terraform` as a local Terraform child module.
The caller owns the existing resource group, provider authentication and state.

## What is necessary?

This is an opinionated foundation, not the smallest possible Container App.

| Part | Reason it is included |
| --- | --- |
| App and managed environment | Hosting resources; this composition owns both rather than sharing an environment. |
| Log Analytics and diagnostic settings | The chosen console/system logging baseline, not a prerequisite for running an app. |
| User-assigned identity | Passwordless ACR/Key Vault/Application Insights access when selected; otherwise a dedicated identity is still created by this foundation. |
| Probes and HTTPS-only ingress | The application health and transport contract; probe timing is a toolkit choice. |
| Staging/production zones, two-replica floor; production resource locks | Toolkit policy, not requirements for every Azure deployment. |
| Private endpoint and DNS zone group | Only for the separate `privateEndpoint` topology; staging and production require this or an internal environment. |
| Internal environment and DNS | `internalEnvironment` creates an internal load balancer and its default-domain private DNS, linked to the infrastructure VNet and any `linkedVirtualNetworkIds`; public network access is disabled. |
| Managed certificate | Only with `customDomain`: a free ACA certificate for one public subdomain. |
| Input guards | Reject invalid references and unsafe combinations before deployment; they do not prove resource existence, permissions or regional capacity. |

The 30-replica ceiling, explicit availability input, public-cloud URL restriction,
Consumption-only compute pairs and the 30-day log retention default are also toolkit choices. Simplifying their
implementation must not silently change those choices or the resource lifecycle.

## Inputs

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Required | Meaning |
| --- | --- |
| `location` | Explicit Azure public-cloud region |
| `appName`, `environmentName` | 2–32 lowercase letters/digits/single hyphens; start with letter, end alphanumeric |
| `stage` | `dev`, `test`, `staging`, `prod`; separate names/groups/state per stage |
| `containerImage` | `registry/repository@sha256:` plus 64 lowercase hex digits |
| `availability` | Explicit fields listed below; no development defaults |
| `resource_group_id` | Terraform only: existing resource group ARM ID |

`availability` contains `minReplicas`, `maxReplicas`, `zoneRedundant`,
`deletionProtection` and an optional `infrastructureSubnetId`. Replicas are
integers: 0 ≤ min ≤ max ≤ 30, max ≥ 1. Development may explicitly choose
`0, 3, false, false` and omit the subnet (null; an empty string is rejected).
**Staging and production require min ≥ 2, zones, a
dedicated subnet and either `privateEndpoint` or `internalEnvironment`;
production also requires deletion protection.** Region, subnet
capacity/delegation and production approval checks remain
[operator gates](REFERENCE.md).

Staging is prod-like where this module decides: topology, zones and the replica
floor, so staging rehearses the production network and failover behaviour.
Cost toggles stay explicit inputs, never inferred from `stage`: `availability`
has no defaults, `deletionProtection` is optional for staging, and
`cpu`/`memory`/`logRetentionDays` keep their small defaults until set.

Optional: `targetPort` (8080), `cpu` (`'0.5'`; Terraform number `0.5`), `memory`
(`1Gi`), `logRetentionDays` (30, range 30–730), `existingIdentityResourceId`
(omitted creates one), `registryServer` (omitted), `secretReferences` (empty list),
`environmentVariables` (empty map), `applicationInsightsConnectionString` (omitted),
`otlpEndpoint` (omitted), `privateEndpoint` (none), `internalEnvironment` (false),
`linkedVirtualNetworkIds` (empty), `publicNetworkAccess` (omitted: preserve
platform/previous setting), `authentication` (none) and `customDomain` (none).
Omitted optional strings are null in both flavours; an empty string is
rejected, never treated as absent.

`cpu` and `memory` must be a Consumption workload-profile pair: cpu 0.25 to 4 in
0.25 steps with memory twice the cpu in GiB (`0.25`/`0.5Gi` … `4`/`8Gi`). Bicep
takes `cpu` as a decimal string because Bicep has no floating-point type.
`logRetentionDays` sets the dedicated workspace retention (PerGB2018 interactive
retention, 30–730 days). `privateEndpoint` holds `subnetId` and
`privateDnsZoneId`. Both must already
exist, and the zone must be `privatelink.<location>.azurecontainerapps.io` for
the module's `location`. See [private access](#private-access-and-public-exposure).

Each secret reference has `name`, `environmentVariable`, `keyVaultUrl`; only HTTPS
Key Vault secret references are accepted, never values. ACR pulls, Key Vault
references and Application Insights require an **existing pre-authorized
user-assigned identity**; no passwords or external RBAC changes. See
[access prerequisites](REFERENCE.md#external-access-and-defaults).

Defaults: Consumption 0.5 CPU / 1 GiB, 30-day log retention, single revision, HTTP scaling,
HTTPS-only external ingress that is public unless the environment is internal,
`publicNetworkAccess` is disabled or `privateEndpoint` is set. The
image must implement `/health/live` and `/health/ready`
on `0.0.0.0:targetPort`. TLS terminates at ingress. Logging uses Azure Monitor
diagnostics, not workspace shared keys. Outputs are resource IDs, the HTTPS
URL, `environmentDefaultDomain`, `privateEndpointResourceId` (null without
a private endpoint), `authCallbackUrl` (null unless browser sign-in is on) and
the [custom domain](#custom-domain-opt-in) DNS values. WAF and regional recovery
are not supplied; Entra authentication is [opt-in](#entra-authentication-opt-in).

Bicep keeps one template: `main.bicep` holds the parameter and output contract
and resources, while types and guards live in `common.bicep`, `environment.bicep`,
`app.bicep` and `auth.bicep`, imported at compile time (no nested deployments
besides `internal-dns.bicep`). Vendor **all** `.bicep` files in `bicep/`.

## Private access and public exposure

With `privateEndpoint` the module disables public network access on the
environment and creates a private endpoint (group `managedEnvironments`) and a
DNS zone group in the supplied zone. The app keeps its `url`; clients in
virtual networks linked to the zone resolve it to the private IP. The
environment refuses other callers. Only inbound HTTP(S) is supported through
the private endpoint.

| Stage | Network access |
| --- | --- |
| `dev`, `test` | Public by default; private topology optional |
| `staging`, `prod` | **Internal environment or private endpoint required**; public network access disabled |

`internalEnvironment` / `internal_environment` requires an infrastructure subnet
and cannot be combined with `privateEndpoint` / `private_endpoint`. It creates
the default-domain DNS zone, VNet link and wildcard/apex A records only when
selected. Bicep uses the packaged `internal-dns.bicep` nested module because ACA
returns the domain at deployment time; include that file when vendoring.
`linkedVirtualNetworkIds` / `linked_virtual_network_ids` adds one link per extra
VNet (hub or peered spokes whose clients resolve the app), named
`<environmentName>-<guid(lowercase VNet ID)>`; IDs must be unique ignoring case
and must not repeat the infrastructure VNet. With `deletionProtection` the zone
carries the same `foundation-protection` lock as the other owned resources.

`publicNetworkAccess` / `public_network_access` is an explicit environment
control, always forced to `Disabled` for either private topology. The platform
accepts only `Disabled` for an internal environment and a private endpoint
needs `Disabled`, so an explicit `Enabled` with either topology is rejected
offline instead of failing or being silently overridden at deployment.

App ingress remains `external=true`: in an **internal environment** this makes
the app reachable from other clients in the VNet, not from the public Internet.
`external=false` instead limits ingress to the same ACA environment and is not
a replacement for internal networking. Remote clients need approved routing and
DNS forwarding. Changing existing environment topology can require replacement;
review the plan, traffic migration and locks rather than assuming an in-place
rollback. The production replica, zone, diagnostic and resource-lock guards
continue to apply to either topology.

### Public exposure

`staging` and `prod` are private. This repository ships no edge, WAF or
global-routing module. To expose staging or production publicly, the operator
must add an edge WAF or gateway outside this kit, for example Azure Front Door
Premium with Private Link to the managed environment (group
`managedEnvironments`, same `location`; the connection stays **Pending** until
an operator approves it, see the
[approval steps](REFERENCE.md#private-endpoint-and-public-exposure)), or
Application Gateway or API Management. Deleting repository sources never
destroys deployed resources, so an edge created earlier stays until an
explicit, reviewed operator action removes it.

**When to add an edge WAF / global routing / gateway later.** Add one for
multi-region active-active or global anycast, for WAF managed rule sets or bot
protection on a public endpoint, or for per-path routing across backends. Add
API Management (see [API Management](../api-management/README.md)) for API
policies such as JWT validation, rate limiting or transforms. Otherwise
Container Apps ingress plus a [custom domain](#custom-domain-opt-in) suffices.

## Custom domain (opt-in)

`customDomain` / `custom_domain` adds one **subdomain** (for example
`app.example.com`) with a free ACA managed certificate validated by CNAME. It
needs a publicly reachable app: it is rejected with `internalEnvironment`,
`privateEndpoint` or `publicNetworkAccess: 'Disabled'`, so staging and
production need an operator-owned edge (see [public exposure](#public-exposure))
with `authentication.publicHostName` instead. Apex domains (A record and HTTP
validation) are not supported. CAA records on the domain, if any, must allow
`digicert.com`.

| Field (Terraform) | Meaning |
| --- | --- |
| `hostName` (`host_name`) | Lowercase subdomain host name without scheme |
| `bindCertificate` (`bind_certificate`) | `false` (default): add the host name unbound and issue the certificate. `true`: bind it with SNI |

Rollout, because the platform validates DNS before it issues a certificate:

1. Deploy without `customDomain`; read `customDomainCnameTarget` (the app FQDN)
   and `customDomainVerificationId` (environment verification ID, not a secret).
2. In the DNS zone create `CNAME <hostName> → customDomainCnameTarget` and
   `TXT asuid.<hostName> = customDomainVerificationId`
   (`customDomainTxtRecordName` repeats the TXT name once set).
3. Deploy with `customDomain: { hostName: '<host>' }`; ACA adds the host name and
   issues the certificate (`<appName>-cert`), which can take several minutes.
4. Deploy with `bindCertificate: true`; ingress binds the certificate (`SniEnabled`).

To remove a domain, reverse the order: deploy `bindCertificate: false`, then
omit `customDomain`, because ACA refuses to delete a certificate that is still
bound. Terraform then destroys the certificate; Bicep `Incremental` deployments
leave it, so delete `<appName>-cert` afterwards. The app must stay running
while the certificate renews.

## Application settings

`environmentVariables` / `environment_variables` is a map of **nonsecret string
values**; for example `APP_POSTGRES_HOST` or `APP_AUTH_SCOPES` containing a JSON
array string. Put credentials in Key Vault and supply their URLs through the
existing `secretReferences` / `secret_references` input. Both reach the same
container: plain settings use `value`; secrets use `secretRef` and
`configuration.secrets[].keyVaultUrl`, never an inline secret value.

Names must match `[A-Za-z_][A-Za-z0-9_]*`. Secret names and environment destinations
must be unique; a plain setting cannot duplicate a secret destination.
Environment-name uniqueness, reserved-name and credential-slot checks ignore case
across plain settings and secret destinations; accepted names keep their casing,
including single lowercase nonsecret settings. The six
telemetry names below are reserved in **both** inputs, even with telemetry off.
`AZURE_CLIENT_SECRET`, `AZURE_CLIENT_CERTIFICATE_PATH` and
`AZURE_FEDERATED_TOKEN_FILE` are reserved too: `DefaultAzureCredential` would
pick them before the managed identity, so neither input may set them.
`APP_POSTGRES_PASSWORD`, `APP_REDIS_URL`, `APP_AI_API_KEY` and
`OTEL_EXPORTER_OTLP_HEADERS` are secret-reference-only destinations. Unknown
credential names cannot be detected automatically: the caller must keep all
credentials out of the plain map, source and preview artifacts.

Defaults remain empty; no settings, credentials or backing services are inferred.
Generated starter roots expose both inputs in their per-environment files.
See [Azure bootstrap](../../docs/bootstrap.md)
for the separate operator-owned identity setup: its **Reader grant is not
sufficient** to deploy workloads, assign identities/roles, write Terraform state
or read Key Vault secret values.

## Telemetry (opt-in)

Setting either telemetry input adds plain environment variables that the
OpenTelemetry SDKs and the Azure Monitor OpenTelemetry distro read, so routing
needs no image change. Omitting both keeps the app configuration exactly
as before.

| Variable | Set when | Value |
| --- | --- | --- |
| `OTEL_SERVICE_NAME` | Either input | `appName` |
| `OTEL_RESOURCE_ATTRIBUTES` | Either input | `deployment.environment.name=<stage>` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | `applicationInsightsConnectionString` | The input, for example the [application-insights](../application-insights/README.md) output |
| `AZURE_CLIENT_ID` | `applicationInsightsConnectionString` | Client ID of `existingIdentityResourceId`, for Entra ID authenticated ingestion |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `otlpEndpoint` | The input, an `https://` OTLP/HTTP base URL such as Langfuse's `/api/public/otel` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `otlpEndpoint` | `http/protobuf` |

OTLP credentials are never plain inputs: add a `secretReferences` entry with
`environmentVariable: 'OTEL_EXPORTER_OTLP_HEADERS'` that points to a Key Vault
secret holding the header string. `secretReferences` must not set the
variables in the table. The managed OpenTelemetry agent is deliberately not
used; see [telemetry routing](REFERENCE.md#telemetry-routing) and
[Langfuse](REFERENCE.md#langfuse).

## Entra authentication (opt-in)

`authentication` turns on Container Apps built-in authentication (Easy Auth)
with Microsoft Entra ID as the only provider. Omitting it creates nothing.

| Field (Terraform) | Meaning |
| --- | --- |
| `clientId` (`client_id`) | Existing Entra app registration client ID (GUID) |
| `tenantId` (`tenant_id`) | Issuing tenant ID (GUID); issuer `https://login.microsoftonline.com/<tenant>/v2.0` |
| `signIn` (`sign_in`) | `false` (default): API mode, bearer tokens only, `401` without one. `true`: browser sign-in, redirect to Entra |
| `allowedAudiences` (`allowed_audiences`) | Extra accepted audiences, such as `api://<clientId>`; the client ID is always accepted |
| `publicHostName` (`public_host_name`) | Host behind an operator-owned edge or other proxy; trusts the standard forwarded-host headers and sets the callback URL |
| `excludedPaths` (`excluded_paths`) | Absolute paths served without authentication, such as `/health/ready` for the deploy health check |

Browser sign-in stores **no client secret**: the module never accepts one and
does not set a client secret setting, so Entra returns an ID token only. The
app gets the signed-in user's claims, not tokens for downstream APIs. See
[why](REFERENCE.md#entra-authentication). Authorization, such as app roles or
groups, stays in the application, using the token claims.

`authCallbackUrl` / `auth_callback_url` is
`https://<host>/.auth/login/aad/callback`, where host is `publicHostName`, else
the `customDomain` host name, else the app FQDN; it is null unless `signIn` is on.

App registration (operator-owned, needs Entra app write access; this module
never creates or edits it). Create the registration before the first deployment
and pass its `appId` as `clientId`:

```shell
az ad app create --display-name <appName> --sign-in-audience AzureADMyOrg
```

With `signIn`, register the callback after deployment, once the URL is known:

```shell
az ad app update --id <clientId> --web-redirect-uris <authCallbackUrl> --enable-id-token-issuance true
```

`--web-redirect-uris` replaces the list; include any existing redirect URIs,
for example one per stage or both the FQDN and custom domain callbacks.
API mode needs no redirect URI; callers request tokens for an audience above
(`az ad app update --id <clientId> --identifier-uris api://<clientId>` sets it).

## Verify and adopt

From the repository root using installed tools:

```powershell
uv run --locked pytest tests\integration\delivery\infra\test_container_apps.py -q
```

Bicep 0.39.26 / Terraform 1.11.3 are the checked compiler baseline;
Azure/azapi is pinned to **2.13.0**. No installers or remote Bicep modules.
Full Terraform validation needs the reviewed provider mirror and native
consumer lock described in [validation](REFERENCE.md#offline-checks-and-pins).
Missing tools/providers are skips, not live validation.

Production locks do not prevent Terraform from removing its own locks during
destroy. Enforce operator approvals. Adding `privateEndpoint` to a running
environment cuts off public clients at once; removing it later does not
reliably reopen public access (see [rollback](REFERENCE.md#rollback)). Before adoption, rollback is removal of
these sources/test; afterward review state, replacements and locks with the
owning tool. See [rollback details](REFERENCE.md#rollback).

Catalog/CI integration and provider-registration profiles remain parent-owned.
No azd service is authored that could overwrite the digest-managed revision.
[Official schemas and release research](REFERENCE.md#verified-official-sources).
