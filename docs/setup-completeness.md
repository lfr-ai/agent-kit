# Complete setup: plan and adoption walkthrough

Use this guide to prepare a reviewed adoption candidate, not production
certification. Start with the [contributor prerequisites](../CONTRIBUTING.md);
the consumer owns its facts, application gates and native-host checks.
See [capability coverage](capability-review.md) for topic-specific work.

## 1. Acceptance plan

| Work item | Acceptance evidence | Prerequisite |
| --- | --- | --- |
| Inventory | Every recorded skill, instruction, role, prompt, script, integration, hook and asset category has a disposition | Recorded source baseline |
| Resource depth | Every canonical skill has a reachable nonempty reference and usable asset; guides give concrete failure cases and gates | Owning audience and prior art |
| Profiles | Each named, portable profile is a compact APM meta-package resolving the catalog's pinned source-package closure | Catalog, manifest and APM dependency checks |
| Instructions | Invariants are path-scoped; consumer facts/knowledge have a distinct owner | Native scope semantics |
| Native roles | Profiles select generated Copilot and Claude role packages by target; installation and frozen replay check their exact output | Native projection contracts and intended-host checks |
| Knowledge/setup | Consumer project/knowledge/adoption/evidence templates and a read-only context check are delivered | Consumer fills actual facts |
| Guards/scripts | Implemented replacements name real files; parser failures have runnable regressions | Explicit accepted input schema |
| MCP | Recorded integrations have native examples, sources, approval and removal steps; delivered servers match the selected manifests | Consumer identity, version and policy review |
| Integrity | Generated profile manifests match the catalog; consumer lock and installed files pass APM audit | Pinned APM |
| Open-source delivery | Community, ownership, workflow, release and publication checks are executable | Operator configures hosted controls |
| Handoff | Full verification and actual APM smoke run after changes; limitations are reported separately | Integrated source |

The [coverage mapping](../.agents/agentic-setup/coverage.json) owns original
identities, replacements and exclusions. [Sources](sources.md) records dated
censuses; [catalog.json](../catalog.json) owns current selection.
Consolidation does not require a separate discovery entry per original.

### Runtime limitation

Static checks do not certify native sessions. Test discovery, authentication,
approval prompts and tool behavior in the intended host; repository verification
does not start or authenticate MCP servers.

## 2. Choose a profile in the consumer repository

The steps below run in the **consumer repository**, not this Agent Kit source
checkout. Choose a [profile](../README.md#choose-a-profile), then add its pinned
package reference to the consumer's root `apm.yml`. For example:

```powershell
name: my-service
version: "0.1.0"
targets: [copilot, claude]
dependencies:
  apm:
    - lfr-ai/agent-kit/profiles/backend#<reviewed-tag>
  mcp: []
```

`backend` groups `shared`, `backend` and target-selected native role packages;
the consumer needs one package reference. APM does not read Agent Kit's `catalog.json`; the source repository
generates a small manifest at `profiles/backend/apm.yml` that declares those
pinned source packages and the selected MCP configuration. APM resolves the
closure; no capability files are copied into `profiles/`.

## 3. Install, compile and audit

```powershell
apm install --target copilot,claude --no-trust-bin
apm compile --target copilot
apm compile --target claude
apm audit --ci --policy ./apm-policy.yml
```

Review the installed output and commit `apm.lock.yaml`. In CI, use
`apm install --frozen --target copilot,claude --no-trust-bin`; it refuses a
missing or stale lock. Use the consumer's reviewed APM policy and keep the audit
in CI. A project-local policy file is not automatically enforced by every APM
0.35.0 install path.

Choose the smallest profile that fits the repository. APM installation does not
narrow a profile to one skill, and a subfolder cannot suppress parent, user or
plugin guidance, models or tools. Use the host's supported skill selection for
task focus; use a separately reviewed workspace when native isolation matters.

### A comprehensive improvement entry point

Select `workflows` for
[`kit-improve-codebase`](../packages/workflows/.apm/prompts/kit-improve-codebase.prompt.md):
read-only discovery followed by requested cleanup, modernization, refactoring
and simplification. Supply scope, goals and constraints; retain convention gates,
behavior protection and evidence-backed completion. The audit facade stays
read-only; choose a narrower prompt when an end-to-end pass is excessive.

In VS Code Local, invoke delivered prompts by slash command or **Chat: Run Prompt**.
Other hosts need discovery/invocation checks. Instructions do not enforce model
compliance or permissions: run consumer tests/lint/types/architecture/naming gates,
and review readability and cognitive load.

## 4. Fill consumer context and wire its gates

Fill the delivered onboarding project-facts, knowledge-index and adoption
templates with actual commands, cwd, versions, owners, architecture, failures,
decisions and recovery. Never copy toolkit facts or another repository's secrets.

The [portable context checker](../packages/shared/.apm/skills/kit-context-onboarding/assets/check_context.py)
accepts `--root <consumer>` and repeated `--entry` paths; defaults are policy,
project facts and agent index. Missing/empty files and broken/escaping local
links fail. Facts, external links, Markdown anchors, domain invariants, licenses
and DI wiring are outside its scope.

Run its `--self-test`, then wire it into the consumer's existing runner.
Keep behavioral, architecture, migration, license and integration gates there;
metadata checks are not replacements.

## 5. Review native roles and host behavior

Consumer APM profiles select generated native role packages for the requested
targets. Role metadata is authored once in skill assets and rendered for both
the native packages and this repository's projections. The
[APM smoke matrix](../scripts/apm_smoke.py) verifies local profile dependency
resolution, exact installed role files, compilation, audit and frozen replay.
It does not prove a published release can be fetched or that an IDE/model obeys
the roles. See [the evidence and deadlines](compatibility.md) and
[native discovery and permissions](editor.md#native-discovery-and-menu).

Use the delivered runtime certification worksheet for discovery, selected/absent
capabilities, read-only edit/shell/delegation denials, bounded implementation,
hook events/cwd and duplicate execution. Roles inherit the caller's model;
certify consumer-added model preferences per host/account.

The session hook is advisory. Native permissions remain authoritative; command
hooks run with user permissions and are not a sandbox. Enforce licenses before
adoption/publication: a post-action hook cannot undo installation.

## 6. Adopt optional MCP deliberately

Follow [MCP adoption](mcp-adoption.md) for current defaults, opt-ins and policy
alignment. Selected `apm.yml` manifests deliver reviewed servers; editor resources
retain examples for all 11 recorded integrations. Workspace auto-start is disabled.
Manifests and examples prove neither authorization nor connection.

1. Identify the concrete missing tool; prefer existing local tools.
2. Choose one server, review its upstream source/license and pin the selected
   package version or image digest. Resolve every `REVIEWED_*` placeholder.
3. Use the native wrapper for the intended configuration location: VS Code's
   workspace MCP file uses `servers`; Claude's root file uses `mcpServers`.
   Other host discovery layers may also consume the root shape; test the actual host.
4. Set consumer-owned authentication and least-privilege scopes without
   committing tokens, headers, sessions or identities.
5. Review APM policy independently; a native file does not override deny defaults.
6. Select only needed tools and test approved read, denied write, declined auth,
   unavailable service, removal and credential revocation.

Registry listings are not security vetting. Review GitNexus licensing, browser
isolation, cloud identity and Postman region/workspace requirements; do not enable
every example merely to match names.

## 7. Validate and refresh owned output

```powershell
task verify -- drift
task verify -- source
task verify -- profiles
task verify -- coverage
task verify -- roles
task verify
task apm:smoke
```

Audit **before** install or rendering can refresh hashes. After canonical edits,
regenerate profile manifests with `task profiles:build`, then repeat source,
profile and drift checks. For this repository's own APM-managed output, use the
pinned APM workflow after auditing it. Do not repair evidence by weakening
policy or hashes.

Replace `<reviewed-tag>` only with a published release that contains these
profile manifests. The APM smoke exercises generated profile dependencies with
local replacements and composed source packages in disposable projects; it does
not certify fetching those dependencies from a published release.

Expect check-only verification and disposable APM delivery; formatting is explicit.
The [verification contract](verification.md) owns smoke isolation, resource-byte
checks, provider-specific compilation and failure behavior.
[Additional regression coverage](capability-review.md#systematic-review-refresh-2026-10-24)
supplements, not replaces, consumer integration tests. Resource inspection runs
neither consumer code nor MCP servers.

## 8. Finish hosted readiness through the operator

Follow the [GitHub checklist](github-setup.md) and [release contract](releasing.md).
Initialization, remotes, hosted controls and publication require operator work;
local files cannot enable or certify them.

Report exact results, unavailable host/cloud checks and operator steps.
Production certification requires actual intended-host and application evidence.

## 9. Migrate, update and roll back

An APM profile is a dependency, not an automatic migration. Never overwrite an
existing consumer's independently owned files.

1. Record the consumer's existing repository, user and plugin capabilities,
   file owners and name conflicts.
2. Audit existing APM output and preserve its lock **before** installation or
   regeneration; regenerating first can erase evidence of modified files.
3. Add one reviewed Agent Kit profile reference to the consumer's `apm.yml`;
   validate the consumer policy and install into a disposable copy first.
4. Compile with pinned APM, inspect the lock and installed files, then verify
   native discovery per host (section 5).
5. Transfer ownership and remove old copies only in the same reviewed change.

Updates: fix portable guidance once in the source repository
([improvement loop](feedback.md)); consumers adopt a reviewed release tag and
commit the lock that records its resolved revision. Project facts, application
tests, private knowledge and memory stay local. Project generators render
profile references rather than copying files
([consumer templates](consumer-templates.md)).

Rollback: keep the previous source, manifests, locks and native settings, and
follow [roll back](feedback.md#roll-back).

## 10. Application readiness and remaining integration

For an application owner, the next action is to choose a deployment target and
the smallest required service set, not to enable every capability. The
[Copier starter](../packages/starter/README.md) is a scaffold and capability
selector, not a fully provisioned platform. A five-minute target can apply to
a warm local scaffold; it is not an established cloud-deployment guarantee.
Tool installation, release availability, approvals, provisioning, DNS and
notification delivery are separate dependencies.

### Configuration ownership

| Concern | Canonical owner | Boundary |
| --- | --- | --- |
| Application settings | The generated app's typed `Settings` class | Process environment overrides local `.env`, then code defaults; validate at startup |
| Infrastructure | One consumer-owned root composition and its environment-specific Bicep parameters or Terraform variable files | The [caller layout contract](../packages/delivery/docs/deploy.md#caller-repository-layout) owns filenames and overrides; deployment does not generate or connect the root composition |
| Resource outputs | The selected infrastructure deployment | Explicitly map endpoints and resource identities into app settings; do not copy credentials into answers or source |
| Secrets | Deployment platform secret references or an approved secret store | Local `.env` is not a production secret store |
| CI/CD | Consumer workflow inputs and protected environment/service-connection settings | Hosted permissions and approvals must be configured by the operator |
| Agent capabilities | Consumer APM manifest, policy and reviewed lock | Installation is separate from application dependencies and native-host certification |
| Development tools | Each tool's dedicated configuration file | Keep Ruff, ty, pytest, coverage, tox, Commitizen and import-linter separate; do not consolidate them into packaging metadata |

There is deliberately no universal settings file for both Python and Azure.
Keep each value with its owner; deployment passes the required outputs into
the app. Choose `iac=none` to omit IaC capability selection. The starter does
not generate infrastructure resources even when Bicep or Terraform guidance
is selected. Infrastructure can live in another repository or remain
operator-managed.

### Ordered completion checklist

| Order | Remaining work | Acceptance evidence |
| --- | --- | --- |
| 1 | Done 2026-11-16: Copier's `jinja2-ansible-filters` license finding, accepted as a dated development-only exception | The unchanged license gate passes; a lock test keeps the package out of shipped closures |
| 2 | Publish an approved release containing the runtime, starter and generated profiles | A clean consumer resolves every immutable pin without local replacements |
| 3 | Choose GitHub Actions or Azure Pipelines, cloud target, IaC ownership and initial services | A short consumer contract with no unresolved deployment inputs |
| 4 | Supply the selected service configuration, compose additional infrastructure and add migrations | Local positive/negative integration tests, then a reviewed non-production preview |
| 5 | Bootstrap cloud trust, network and state; configure environment gates | OIDC/WIF login with least privilege; unauthorized deployment is denied |
| 6 | Connect image build, scan, immutable promotion and deployment | One successful hosted run, post-deploy health checks and a tested rollback |
| 7 | Connect monitoring and notifications | A controlled failure reaches the intended Teams channel; telemetry is received without sensitive data |
| 8 | Exercise production operational controls | Restore drill, backup/retention policy, secret rotation, load/rate-limit checks and named incident owners |
| 9 | Certify the selected agent and AI behavior | Intended-host discovery/permissions checks and use-case evaluations, not just file validation |

The [delivery inventory](../packages/delivery/catalog.json) supplies 17 separate
Azure compositions and GitHub/Azure Pipelines entry points. The optional
[API deployment scaffold](../packages/starter/DEPLOYMENT.md) connects a
development Container App, telemetry and optional alerts; it is not an assembled
production application stack. Application Blob Storage and Terraform-state
storage are separate modules. Cosmos DB is an opt-in composition; Service Bus,
App Configuration and AKS are not shipped compositions.
Non-Azure ECS and Cloud Run APM examples are adaptation templates, not a
configured alternate deployment selected by Copier.

### Application feature boundaries

| Area | Available building block | Still required in the application |
| --- | --- | --- |
| HTTP | FastAPI runtime, health routes, safe error responses, request IDs and structured access logging | Business routes and readiness probes for additional dependencies |
| Authentication | Optional generated Entra bearer lifecycle and protected technical route; runtime browser-session/callback implementation | App registration, consent, business route authorization, browser-session wiring/storage and callback origins; other OIDC providers need an adapter |
| Rate limiting | Optional generated in-memory or Redis counters and Redis lifecycle | Quotas, trusted proxies and failure policy; outages currently fail open |
| Data | Optional generated PostgreSQL lifecycle/readiness and local Compose service profiles; runtime Redis identity/rate-limit adapters | Schema/migrations, credentials, TLS, backups and general cache behavior |
| Telemetry | Runtime logging and optional OpenTelemetry tracing | Exporters, sampling, log/metric export, retention and receipt tests |
| AI and retrieval | Optional generated internal text generator; runtime Azure Search retrieval and Document Intelligence OCR | Provider authentication, model/index setup, retrieval/OCR wiring, ingestion, authorization and answer generation; non-Azure retrieval/OCR adapters are not included |
| Agents and LLMOps | APM LangGraph, prompt-management, Langfuse and evaluation templates | SDK/service adoption, persistence, datasets, quality thresholds, promotion/rollback and operational ownership |

Runtime feature settings are explicit typed objects. The starter's single
`APP_*` settings adapter configures selected PostgreSQL, Redis, Entra bearer
and text-generation integrations; disabled services are not imported.
Installing another runtime extra alone does not wire that feature into the app.
Principal-keyed rate limits also need
authentication middleware before the limiter; route guards alone are not that
middleware.
Generated IaC accepts nonsecret environment strings and existing Key Vault
references in its per-environment parameters. It does not infer endpoints,
create the selected database/Redis/model services, or grant their access.
PostgreSQL can explicitly use a user-assigned managed identity instead of a
password; database user mapping and grants remain operator-owned.

Azure Search hybrid ranking is not a Self-CRAG implementation. The corrective
retrieval APM template is separate adopt-and-wire code, not an installed
retrieval strategy or a quality result. Hydra, graph databases and additional
retrieval frameworks are workload decisions, not prerequisites for every app.
No general ML training/deployment platform is generated.

Azure alerts use email receivers or a caller-owned action group. Teams is
preferred through an operator-owned integration with payload transformation,
connection ownership/co-owners and a delivery test; email-only is also supported.
The starter references the existing group by ARM ID, leaving receiver secrets
and configuration outside its plans and state. The ID alone proves neither
configuration nor delivery. Staging/prod require a destination; dev/test can
explicitly opt out.
They are not automatic CI-failure notifications. Use the
[alert operator contract](../packages/delivery/infra/container-apps-alerts/REFERENCE.md).

### Decisions needed from the operator

- CI host and repository visibility/plan; confirm which hosted approval controls
  are available.
- Azure region, environment names and service set; for non-Azure, name the
  actual target rather than assuming a generic cloud deployment.
- Bicep, Terraform, external infrastructure, or no managed infrastructure.
- Identity provider and client flow: API tokens, browser login/callbacks or
  both; tenant and role boundaries belong to the consumer.
- Teams channel/workflow owners, telemetry retention, budget and recovery
  requirements. Do not put secret webhook URLs into issues or documentation.
- Release authority and the reviewed development-only license decision.

The [Azure bootstrap](../packages/delivery/docs/bootstrap.md) emits an offline
plan and offers explicit target-checked operator apply for resource-group
ownership, managed identity, federation and Reader access. It does not inspect
the current account in plan mode, grant deployment permissions, configure
hosted CI environments or create a Terraform backend.

Until these choices and live checks are complete, report the kit as reusable
building blocks and an opt-in local application scaffold, not a certified
production deployment or a measured five-minute cloud installer.
