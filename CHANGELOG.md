# Changelog

Notable changes, following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- **Executable starter options:** opt-in PostgreSQL, Redis rate limiting,
  Entra bearer validation and internal text generation with typed application
  settings, selected dependency lifecycles and local service profiles.
  Structured request logging replaces raw Uvicorn access URLs. Application
  setup and startup no longer require APM installation. PostgreSQL supports
  explicit user-assigned managed identity without ambient CLI credentials.
- **Starter delivery:** API projects require an explicit reviewed toolkit
  commit for runtime and reusable workflow references. Optional development
  IaC uses immutable Terraform module references or offline Bicep vendoring
  with provenance, plus a manual image-digest deployment workflow. Choosing
  no IaC emits no cloud deployment scaffold. Caller-owned nonsecret settings
  and Key Vault references configure selected services; existing action groups
  support operator-configured Teams receivers without exposing webhook URLs.
  Azure-deployed API starters export traces to Application
  Insights through a trace-only Azure Monitor exporter as the runtime
  managed identity; log export stays off so only sanitized console logs reach
  Log Analytics, and local runs import no Azure SDK.
- **Azure bootstrap:** `task bootstrap:azure` produces an offline plan from
  explicit tenant, subscription and reviewed OIDC claims. Operator-only apply
  verifies the target before creating an owned resource group, managed identity,
  federated credential and RG-scoped Reader assignment. Opt-in
  `--access deploy` instead grants Contributor and a Role Based Access Control
  Administrator assignment whose condition allows only the templates'
  data-plane roles for service principals.
- **Private networking and least privilege:** an opt-in network composition
  provides a spoke virtual network, delegated apps subnet, private-endpoint
  subnet, NSGs and optional private DNS zones. Container Apps environments
  accept a private endpoint, and staging and production require it or an
  internal environment; public exposure needs an operator-owned edge WAF or
  gateway. Storage grants the runtime
  identity Blob Data Contributor. The identity and network guide documents
  every identity, role ID, private endpoint and stage gate, and a test keeps it
  in sync with the templates.
- **Blob storage:** the Storage account composition is complete and registered
  in the delivery catalog, with Entra-only access and production private
  networking, retention, diagnostics and deletion protection.
- **Entra sign-in and custom domains:** Container Apps can enable Entra built-in
  authentication (secretless API or browser sign-in, callback URL output) and
  bind a public custom domain natively with a managed certificate and DNS
  record outputs, in Bicep and Terraform. Front Door is not part of the
  default path.
- **Post-deploy health check:** the GitHub and Azure Pipelines deploy paths take
  an optional HTTPS health URL and fail the deployment unless it answers `2xx`.
- **Document database:** an opt-in Cosmos DB for NoSQL composition in Bicep and
  Terraform with Entra-only access, an optional database, containers and
  Built-in Data Contributor assignment; serverless in dev/test, while
  production adds autoscale, zone redundancy, continuous backup, a private
  endpoint, diagnostics and a deletion lock.
- **PostgreSQL extensions:** an optional `extensions` input allow-lists server
  extensions such as `vector` and `age` in both Bicep and Terraform.
- **Starter debugging:** API projects include one VS Code `API` launch that
  runs the same Uvicorn command as `task start` under debugpy.
- **Azure-native selection guide:** infrastructure review and retrieval skills
  prefer managed, Entra-only Azure services (AI Search hybrid ranking with RRF,
  Storage without shared keys, Managed Redis) before self-hosted software.
- **Faster development loop:** `task check` fixes formatting and lint, type
  checks, checks imports and runs unit and property tests except `slow`
  whole-catalog guards (215 s instead of 664 s on a 4-core laptop). Repository-wide,
  network and Docker hooks moved from pre-commit to pre-push; local hooks reuse
  the locked environment without syncing; CI runs both stages and `task verify`
  and verifies branches once through pull requests. Generated API projects gain
  `task check`; the exported pre-commit template runs unit tests and pin checks
  at pre-push.
- **Capability selection:** internal Python library workflows resolve catalog
  profiles and optional skill allowlists for maintainer tooling. Consumers
  install a generated APM profile meta-package; no Agent Kit executable is
  required.
- **Infrastructure packages:** optional `terraform`, `bicep` and `remote-access`
  profiles let projects install only the tools they use.
- **Expanded guidance:** skills, instructions, prompts and templates for backend
  APIs, authentication, databases, frontend design and identity, LLM evaluation
  and agents, infrastructure, and cross-stack contracts.
- **Shared workflows:** project memory, handoffs, feedback loops, specification
  work, codebase audits and modernization. Coordinator roles can use workers
  from optional packages without requiring them in every installation.
- **Kit improvements:** `/kit-improve` helps correct reusable guidance at its
  source instead of maintaining local copies.
- **Convention and context guards:** the Python checker's default `acronym-case`
  rule requires uppercase acronyms in class and type alias names (`LLMClient`,
  `SQLAlchemyUnitOfWork`); template classes are renamed without aliases. Repository
  tests require unique "Use when" skill descriptions, and CI checks pull request
  commit messages with `cz check`. Coordinators and `kit-debug` hand the final
  diff to `kit-code-reviewer` for a second pass.
- **Skill evaluations:** synthetic cases and a result checker distinguish
  complete observations from missing evidence. Model runs remain explicit;
  evaluations never publish changes automatically.
- **Hooks and MCP through APM:** `shared` ships an always-on Git-guard hook
  (Git read-only outside the kit checkout, no hook bypass, no push) and each
  package declares its reviewed MCP servers in `apm.yml`. `task verify -- source`
  validates these declarations against closed schemas and the policy allow list.
- **Git guard resource:** a Git policy for the existing tool guard, now delivered
  as the `shared` hook. A kit-checkout exception is scoped by `AGENT_KIT_DIR`.
- **Developer setup:** dedicated tool configuration, Task and VS Code templates,
  a pinned dev container, and unit, property and integration test tiers with a
  90% branch-coverage gate.
- **Checkout discovery:** Task, workspace terminals and dev-container sessions
  receive `AGENT_KIT_DIR`. Windows bootstrap registers the clone for future
  sessions; `task checkout:register` refreshes a moved clone.
- **Release tasks:** `task version:preview`, `task version:prepare` and
  `task release:build` simplify versioning and artifact checks.
  `task release:publish TAG=vX.Y.Z` requires operator confirmation and an
  existing draft. Changelog entries remain manually curated.
- **Verification:** template parsing, resource completeness, context budgets,
  Python conventions, architecture and native-delivery checks.
  `task test:matrix` runs the isolated tox environments.
- **Edit feedback hook:** an advisory `PostToolUse` hook for Copilot and Claude
  returns ruff and convention findings for each edited Python file, so agents
  fix them in the same turn. It never blocks; `task verify` remains the gate.
- **Hosted integrations:** Codecov OIDC uploads, CodeRabbit configuration,
  CodeQL, OpenSSF Scorecard and reviewed draft releases with checksums and
  attestations. Apps, rulesets and environment protections need separate
  operator activation.
- **Consumer resources:** adoption, knowledge, runtime certification and
  opt-in MCP templates with explicit trust and removal guidance.

### Changed

- **Runtime names:** public `platform_kit_runtime.ai` names and internal adapters
  use uppercase acronyms (`AIError`, `AIMessage`, `EntraJWTValidator`) before the
  first release; enum values and wire formats are unchanged.
- **Smaller agent picker:** the main roster is `kit-orchestrator` and
  `kit-debug`. `kit-tdd`, `kit-fullstack`,
  `kit-frontend` and `kit-ai-engineer` were folded into `kit-orchestrator` and
  its workers; `kit-refactor` is now a worker. The `readonly` tier is removed, so
  every role can inspect history, diffs and offline checks.
- **Fewer worker roles:** `kit-plan-architect` merged into `kit-planner`,
  `kit-solid-review` into `kit-code-reviewer` and `kit-modernization` into
  `kit-deep-thinking`. The repository-only, shell-less `kit-reviewer` is removed;
  use `kit-code-reviewer` or the `kit-review-change` prompt instead.
- **Consumer tooling:** exported type gates use ty. Optional JavaScript MCP
  examples use Bun explicitly and still require review before activation.
- **Migration required:** Terraform, Bicep and remote-access capabilities moved
  out of `iac`. Add `--feature terraform`, `--feature bicep` or
  `--feature remote-access`, or install the matching package, to retain them.
- **IaC selection:** `kit-iac-selection` is now part of `kit-infra-review`.
- **Lower context load:** duplicate instructions are consolidated and skill
  descriptions are shorter. Existing catalog budgets are unchanged.
- **APM delivery:** on-demand skill trees are excluded from application context
  scans. Smoke tests cover every portable package in budget-compliant selections.
- **Role models:** native roles inherit the caller's model instead of pinning
  models that a host may not provide.
- **Solo-maintainer reviews:** the committed default-branch ruleset permits an
  admin bypass through pull requests only. Applying it remains an operator step.
- **Build backend updates:** `hatchling` is updated manually because Dependabot
  does not synchronize its build constraint in the lockfile.
- **Experiment configuration:** typed templates use one schema for versioned
  LLM evaluation sweeps, including model, prompt, dataset, temperature and seed.
- **Maintainer module layout:** module names no longer repeat their layer's
  role. Adapters live in `infrastructure/apm.py`, `catalog.py` and `output.py`;
  `application/services/` is flattened into `application/`; the unused catalog
  port is removed; and the runtime LiteLLM adapter is `infrastructure/litellm.py`.
  `core/primitives.py` now owns source primitive file names and each native
  runtime's agent and prompt locations.

### Fixed

- **Storage teardown:** the production Terraform deletion lock is removed
  before its managed child resources, with an offline dependency-graph regression.
- **Runtime input validation:** identity origins reject port 0 and host
  characters outside hostnames or bracketed IPv6; AI `api_base` rejects an empty
  query or fragment marker.
- **Standalone scripts:** complete PEP 723 metadata declares empty dependency
  lists. Script process-boundary tests use subprocess timeouts that clean up
  child processes.
- **Windows reliability:** bounded retries handle transient publication locks
  without overwriting outputs. APM output no longer depends on console encoding.
- **Launcher isolation:** APM smoke uses the toolkit launcher beside the active
  interpreter, not an unrelated executable on `PATH`.
- **Source inventory:** Git internals, installed dependencies, tool caches and
  bytecode no longer pollute composition.
- **Provenance:** noncanonical paths and unowned native prompt files are
  rejected without weakening hash or ownership checks.
- **Validation:** Markdown link checks no longer mistake Python expressions for
  links; OpenAPI path maps, recorded streams and portable templates reject
  invalid input more consistently.
- **Type coverage:** scripts, guard code and portable Python assets are included
  in type checks rather than silently skipped.
- **Markdown comments:** portable memory, handoff and debt checkers recognize
  the `--!>` closing form.
- **Edge templates:** nginx, Caddy and Traefik start HSTS at 300 seconds to match
  the documented staged rollout.
- **Dependency review:** pull-request checks use the required base/head diff;
  merge-group verification stays in the main CI matrix.

### Security

- **Dependency fix:** GitPython 3.2.1 resolves CVE-2026-114145.
- **Supply-chain checks:** bootstrap audits locks before full installation.
  Dependency audits, license checks and immutable tool pins are enforced by
  the repository gates; version updates have a 14-day cooldown.
- **Agent safeguards:** native permission rules cover package installation and
  publication. Optional guards remain defense in depth, not a sandbox.
- **Private reporting:** public issue intake directs security reports to the
  private advisory channel.

## 0.1.0 - 2026-10-08

### Added

- Original APM-first capability bundles, strict policy, profile composition,
  provenance verification, native repository adapters, and quality gates.
