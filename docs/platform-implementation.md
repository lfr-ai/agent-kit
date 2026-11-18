# Platform integration

For contributors and operators choosing a generated application architecture.
Use this guide to distinguish automatic wiring from the setup and qualification
that must precede an approved deployment. Agent, delivery, runtime and starter
packages remain independent; a separate workstation project owns machine setup.

## Boundaries

| Owner | Responsibility | Must not own |
| --- | --- | --- |
| Agents | APM source, combined profiles, native agent projections | Application state, business logic or a custom consumer installer |
| Delivery | Reusable CI, policy checks and Azure infrastructure | Runtime middleware or application business logic |
| Runtime | An independently installable Python library with opt-in adapters | Copier, APM resolution or cloud provisioning |
| Starter | Consumer-owned project files and references to reviewed packages | Hand-maintained copies of skills, agents, instructions or hooks |
| Workstation | Explicit operator-controlled installation and prerequisite checks | Application deployment, credentials or automatic personal settings |

APM remains usable without the runtime library. The runtime remains usable
without APM. Application code does not import the starter or delivery tooling.
Infrastructure uses Azure initially; application hosting and LLM provider
configuration are separate choices. Local Docker and on-premises execution
must not require Azure.

## Default application architecture

```text
Internet (dev/test) or connected VNet (staging/prod)
  -> Container Apps native HTTPS ingress -> API + runtime managed identity
       |-> selected PostgreSQL / AI / Key Vault through required network + DNS
       |-> structured stdout/stderr -> ACA collection -> environment workspace
       `-> optional traces -> Application Insights -> same workspace

ACA Requests / RestartCount -> Azure Monitor rules -> action group -> Teams/email
Terraform remote state -> separately bootstrapped, protected Azure Blob storage
```

Local execution uses the same application on loopback, with no Azure identity,
workspace or exporter required. Bicep uses incremental ARM deployment rather
than Terraform state. An optional subscription audit deployment can export
Activity Log events to the selected workspace; it is not part of each app.

| Decision | Why |
| --- | --- |
| Keep native hosting and private DNS/networking | ACA already handles ingress, TLS and scaling. Private data and staging/prod reachability remain explicit. |
| No default Front Door or APIM | Domains alone do not justify an edge. Optional APIM remains for its actual token, quota and other API policies. |
| One new-stack application workspace | Console/system diagnostics and optional Insights share retention/access ownership without an identity dependency cycle. Existing deployments require migration review. |
| Console logs; optional trace export | Keep useful sanitized diagnostics locally and centrally without a duplicate SDK log pipeline. Resource creation alone does not instrument the API. |
| Existing action group or email receivers | Teams integration is operator-owned, not a new notification service. Staging/prod require an explicit destination. |
| Separate backend and subscription audit | Their ownership/lifecycles are broader than one application. No automatic stack/state recreation or compliance claim. |
| No Ansible or other configuration management | There are no VMs or long-lived hosts to configure. Bicep/Terraform declare Azure resources, immutable container images carry the OS and app, and the az CLI bootstrap covers one-time identity and state setup. Reconsider only if self-hosted runners or VMs become stack-owned. |

An edge WAF, multi-region routing/failover or global caching can justify
Front Door later; explicit API policies can justify APIM. Neither is added
just for a custom domain. **ACA ingress is not WAF coverage.** This starter
does not supply a migration for an existing public WAF-protected deployment.
Retain that boundary and review origin bypass prevention, traffic/DNS cutover
and rollback before moving any protected route. Removing repository sources
does not authorize deletion of a deployed gateway, WAF or DNS record.

## Automatic versus operator setup

"Automatic" below means after reviewed inputs and an approved pipeline apply,
not while Copier generates files.

| Responsibility | Automatic wiring | Required operator setup/evidence |
| --- | --- | --- |
| Application/agents | Generate only selected app, IaC, CI and APM references | Review a published immutable toolkit revision and install reviewed locks; APM setup is separate from local app startup |
| Hosting/network | ACA, native TLS, replicas, probes, selected VNets/private DNS and endpoints | Region/CIDR/resource names, quotas, private runner routing and DNS; external domain registration and certificate validation |
| Identities/secrets | Runtime managed identity and selected scoped assignments; Key Vault secret references, not secret values | CI federation, target resource group, reviewed deployment authority, vault permissions/reachability, PostgreSQL database-principal grants |
| Entra authentication | Selected bearer validation and technical authorization boundary | API registration/audience/scopes/roles and business authorization; no automatic browser callback registration |
| Terraform state | Remote backend configuration and separate stage keys | Bootstrap/protect storage first, scoped state identity, network access and recovery rehearsal; never publish state as a preview artifact |
| Diagnostics/tracing | Console collection; optional explicitly selected Insights trace integration | Retention/residency/access policy, actual ingestion/query checks and costs; keep historical workspaces during migration |
| Alerts | App metric rules and either email group or existing-group reference | Real receivers, Teams workflow authorization/connections, incident owner, action-group test and controlled non-production firing/resolution |
| Subscription audit | Separate opt-in Activity Log export and selected notifications | Deploy once per subscription, avoid duplicate exports, select categories/retention; Entra and business auditing need separate coverage |
| Delivery | Digest-owned image, preview/apply and selected CI templates | Protected environments, least-privilege federation, private runners and hosted approval/bypass checks |

See the [deployment guide](../packages/starter/DEPLOYMENT.md) for inputs,
bootstrap, identity and retained-data migration steps. The
[development loop](agentic-development-review.md#fast-feedback-and-context-ownership)
keeps full platform validation out of the per-edit path. The
[official-source review](sources.md#infrastructure-and-feedback-loop-review-2026-11-16)
records the platform contracts behind these decisions.

## Available foundation

Contributors should use this inventory to distinguish reusable source from
unfinished application features. None of these entries alone makes the
toolkit release-ready or production-certified.

| Component | Implemented scope |
| --- | --- |
| Agents | 43 portable profiles, including 31 combined starters; generated native packages with 18 roles per selected host |
| Delivery | Reusable Python/Bun/IaC checks and Azure deployment for GitHub and Azure Pipelines, Renovate presets, and the [delivery infrastructure inventory](../packages/delivery/README.md) in Bicep and Terraform |
| Runtime | Independent Python package with health/readiness, optional Entra BFF/bearer identity, Redis sessions, Graph profile access, LiteLLM text inference, and installed-distribution tests |
| Starter | APM onboarding manifests, an optional FastAPI application with selected PostgreSQL/Redis/Entra/text-generation wiring, Docker, Compose and CI, plus optional Bicep/Terraform for `dev`, `test`, `staging` and `prod` that provisions the selected PostgreSQL and AI services (cloud Redis is rejected until its keyless client lifecycle is supported); no installation hooks |
| Workstation | Separate source with native Windows manifests, read-only plans, explicit Windows apply with isolated tests and a read-only Windows CI workflow that has not run hosted; no machine configuration performed |

The [compatibility contract](compatibility.md) records actual APM smoke evidence.
The starter's development-tool license exception is documented below; it is not
a license for generated applications. Runtime adapters and copyable guidance
are not complete business applications. Hosted Azure
qualification, remote-release consumer qualification and end-to-end machine
installation require separate evidence.

### Operational defaults

The target environment contract is `local`, `dev`, `test`, `staging`, and `prod`.
`local` means application/Compose execution, not an Azure deployment. Cloud
parameters, state, identities, approval rules and secrets belong to the selected
environment. See the [starter deployment contract](../packages/starter/DEPLOYMENT.md)
for implemented coverage and prerequisites; this target list alone is not
deployment evidence.

- Use Container Apps' native HTTPS termination, reverse proxy and load balancing
  rather than installing another proxy by default. Local loopback HTTP does not
  imply that production HTTP is allowed. A custom domain and certificate require
  the domain owner's configuration.
- Keep environment reachability separate from app ingress. An internal
  Container Apps environment with app ingress `external` is reachable from its
  VNet, not the public internet. Environment-only app ingress is more restrictive.
  An environment private endpoint is another topology, requiring public network
  access to be disabled and private DNS; do not add one merely because a VNet
  exists. Private data-plane checks need a runner with the required routing/DNS.
- Redis rate-limit counters are not a general application cache. Keep sensitive
  API responses uncached by default. Adopt response caching only with explicit
  authorization-aware keys, expiry and invalidation. Rate limiting does not
  replace authentication, authorization or a hard inference spending limit.
- Keep consultant deployments independent: no embedded customer identifiers,
  copied credentials, ambient Azure account selection or shared environment
  state. Caller-owned region, DNS, administrator and model choices cannot be
  inferred safely from a workstation login.
- Chezmoi owns personal dotfiles; workstation setup owns explicit prerequisite
  installation. Neither application generation nor deployment should apply
  personal settings. A private Git repository is not a secret store: prefer
  password-manager references, or reviewed encryption when secrets must be
  versioned.

Sources: [Container Apps ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview),
[internal environments](https://learn.microsoft.com/en-us/azure/container-apps/vnet-custom),
[private endpoints](https://learn.microsoft.com/en-us/azure/container-apps/how-to-use-private-endpoint),
[GitHub environment protection](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment),
and [chezmoi secret management](https://www.chezmoi.io/user-guide/password-managers/).
Hosting-plan protection availability and successful real-machine/cloud execution
must be checked separately from local configuration tests.

### Runtime code is not the template catalog

| Capability | Current delivery |
| --- | --- |
| FastAPI, lifespan, health/readiness | Executable [runtime composition](../packages/runtime/src/platform_kit_runtime/composition.py); consumers own business routes and resource lifetimes |
| Settings, configuration loading, dependency registry/container | Explicit runtime configuration records and injected ports; generated applications have one typed `APP_*` settings adapter. Further loaders and application containers remain [configuration](../packages/backend/.apm/skills/kit-config/) and [FastAPI](../packages/backend/.apm/skills/kit-fastapi-service/) templates |
| Middleware, request/correlation context, access/HTTP logging | Runtime installs correlation and content-free access logging; the starter configures a console handler and disables raw Uvicorn access URLs. Exporters and other middleware remain opt-in |
| Structured logging, exceptions, problem responses | Runtime supplies opt-in sanitized JSON console logging and correlation; the starter selects application logging and configuration-error fields without request content |
| DTOs, value objects, enums, response models | Capability-specific runtime records and models; no universal domain/base-model framework |
| HTTP/chat client, retries | Optional LiteLLM text-only client and identity-specific HTTP transports; bounded retries/deadlines, not a general streaming/tool-calling client |
| Incoming rate limiting, general cache, circuit breaking | Runtime provides opt-in fixed-window limiting; cache and circuit-breaker adoption remains separate |
| Redis | Executable identity/session and shared rate-limit stores; general-purpose caching remains a template |
| SQL, ORM, database manager, base models, migrations | Runtime SQLAlchemy/asyncpg lifecycle and readiness; application schemas/migrations remain consumer-owned [persistence](../packages/backend/.apm/skills/kit-sql-persistence/) |
| Authentication, authorization, RBAC, callbacks | Optional Entra bearer/BFF runtime; applications still own resource-level authorization |
| RAG/retrieval | Runtime chunking, embeddings and scoped Azure AI Search; [retrieval templates](../packages/ai/.apm/skills/kit-retrieval/) cover further strategies. A complete answer pipeline is not automatic |
| OCR | Optional Document Intelligence runtime adapter; provisioning and ingestion wiring are consumer-owned |
| Langfuse | Prompt/evaluation templates and runtime OTLP tracing instructions; not an installed Langfuse service |
| DSPy, Hydra | Optional evaluation/experiment guidance; neither is a required or integrated runtime dependency |
| Azure Container Apps | Native Bicep/Terraform [composition](../packages/delivery/infra/container-apps/); no live deployment claim |
| CI/CD, DevOps, pre-commit | Reusable checks and hook templates exist; complete consumer promotion pipelines remain adaptation work |
| Starter | [Optional API scaffold](../packages/starter/README.md) plus explicitly selected APM guidance; not a complete business application |

The Windows operator apply workflow has offline fake-native execution coverage.
Real installers, UAC, reboots and restoration of machine state remain untested;
uninstall is not a transactional rollback. No machine installation was executed.

Authorization role combinations must be explicit during adoption: the runtime
requires all supplied roles, while the identity access-policy template currently
accepts any supplied role. Do not substitute one for the other silently.

## Feature qualification targets

These are distinct capabilities, not refactor acceptance criteria:

- Retrieval should use the maintained LlamaIndex/LiteLLM integration behind a
  typed retrieval boundary. Ingestion, deletion, access filtering, citation
  provenance and evaluation must be tested before offering a RAG starter.
  FAISS, fusion and corrective retrieval are options to evaluate against a
  measured baseline, not mandatory dependencies in every AI application.
- New Azure OCR adapters should target the generally available Document
  Intelligence `2024-11-30` API and `prebuilt-read` first. Resource provisioning,
  document limits, cancellation and sanitized SDK failure handling are separate
  acceptance obligations.
- Langfuse's current line is v4 (v4.76.0 when checked on 2026-11-06), not v3.
  Its official Azure Terraform deployment targets AKS. Container Apps for the
  stateless web/worker containers is therefore a toolkit-owned integration,
  not an upstream-supported Azure deployment template. Keep durable databases,
  queues and object storage outside those app containers, and qualify the
  chosen ClickHouse hosting, persistence and recovery explicitly.

Sources: [LlamaIndex LiteLLM integration](https://github.com/run-llama/llama_index/tree/main/llama-index-integrations/llms/llama-index-llms-litellm),
[Document Intelligence versions](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/overview?view=doc-intel-4.0.0),
[Langfuse release](https://github.com/langfuse/langfuse/releases/tag/v4.76.0),
and [Langfuse Azure infrastructure](https://github.com/langfuse/langfuse-terraform-azure).

## Implementation sequence

Each row is a separately verified change, not a claim that the entire platform
is implemented.

1. Establish the baseline, pin the tested APM version, and deliver both primary
   agents and all workers through target-specific APM packages.
2. Add finite combined profiles within the existing context budgets. Preserve
   standalone profiles and reject untested combinations.
3. Integrate reusable delivery sources without changing the source checkout;
   preserve root GitHub workflow entry points and Azure Pipelines contracts.
4. Establish the installable runtime foundation, then qualify identity/Graph and
   provider-neutral inference as separately installable capabilities. Retrieval
   remains a later, independently scoped adapter.
5. Add a Copier starter whose answers select a combined profile and runtime
   extras. Generate manifests; let APM install, compile, audit and lock
   capabilities. Do not execute installation as a Copier generation hook.
6. Add Azure Container Apps compositions in Bicep and Terraform, then integrate
   their catalog and caller CI checks. `azd` orchestration remains deferred until
   a caller can deploy the digest-owned revision without overwriting it.
7. Prepare the separate workstation source with dry-run, backup and isolated
   tests. Never install tools or change personal settings as part of kit tests.
8. Perform installed-artifact, generated-consumer and update/rollback testing,
   followed by explicitly approved publication and hosted qualification.

Physical relocation follows verified contracts. Do not combine a failing
baseline, wholesale directory movement and new runtime behavior into one change.
No remote rename, repository creation, commit, push or cloud deployment is
performed by these local verification steps.

## Acceptance evidence

- Every offered combined profile must fit the unchanged discovery budget.
- APM must install the exact native roster and target-specific metadata in
  disposable consumers, including single-target and combined-target installs.
- Frozen installation must preserve the reviewed lock and installed content.
  Edited or colliding owned files remain errors.
- Generated projects must use the tested APM pin and commit their own APM lock.
  Dependency bots are not assumed to understand APM manifests; a verified
  update integration is required before claiming automatic APM updates.
- Runtime tests must exercise the installed artifact away from its source,
  failure statuses, timeouts and credential-free diagnostics.
- Untrusted pull requests run offline/static validation without deployment
  credentials. Credentialed previews and deployments require separately
  authorized identities and environments.
- Manual workflow dispatch is not equivalent to independent approval.
  Unsupported production protection must fail closed; repository visibility
  and license are independent decisions.
- Stateful ClickHouse on Container Apps is unqualified until restart,
  persistence, storage compatibility, backup and recovery tests pass.
  Running a Docker image alone does not establish production readiness.
- Application, native IDE, hosted CI and cloud evidence are distinct. File
  tests must not be presented as certification of any of those runtimes.

## Current baseline limitation

The obsolete local APM receipt has been recovered through a verified,
public-CLI historical-source rollback followed by current-source installation.
`task verify -- drift` now passes all 31 checks without changing current
generated bytes, authored source, or policy. The
[compatibility contract](compatibility.md#legacy-deployment-ledger-recovery)
documents the recovery and its limits.

The Copier 9.19.1 development dependency brings
`jinja2-ansible-filters==1.3.2`. Its source is genuinely GPL-3.0-or-later;
the installed `GPL3` metadata is not merely a packaging error.
No released Copier version supports the required modern template features
without this unconditional dependency, and upstream replacement work in
[copier-org/copier#2039](https://github.com/copier-org/copier/pull/2039)
remained an unmerged draft when rechecked on 2026-11-16. The owner accepted it
on 2026-11-16 as development-only tooling through a dated, scope-tested
exception; see the [development-tool license
decision](dependency-security.md#copier-development-tool). GPL licenses stay
denied for every other dependency.
