# Capability review and implementation plan

This is a source and tooling review, not a production or hosted-runtime
certification. The repository is a Python CLI and reusable capability library:
it is not a running web application, model service, database cluster or cloud
deployment. Consumer-specific controls belong in the consumer's own tests.

## Acceptance criteria

- Extend a canonical owner first. Add a dedicated skill only for a distinct task
  family that needs its own procedure, resources and tests.
- Every added resource is reachable, relocatable, syntactically valid and useful
  for a named task. New behavior receives positive and negative tests.
- Keep catalog description, instruction and body budgets unchanged; shorten
  descriptions or split selections instead of raising a budget. New roles use
  the existing permission tiers. Detailed provider knowledge belongs in
  task-loaded references.
- Keep credentials, local paths, private project context and realistic secrets
  out of portable resources.
- Preserve error behavior, fail on invalid inputs, and do not add dependencies,
  network calls or implicit third-party execution just to illustrate a tool.
- Run source, resource, conventions, type, test and dependency gates, then the
  actual released APM install/compile/audit/provenance smoke.
- Distinguish unavailable native, model, database and hosted checks from passed
  local checks. A manifest, template or matching server name proves no runtime.

## Ordered work and ownership

| Step | Owner | Deliverable | Acceptance evidence |
| --- | --- | --- | --- |
| 1. Establish baseline | Maintainer | Existing catalog/resource census and full-hook result | `task verify`, `scripts.check_resources`, hooks |
| 2. Map requested topics | Maintainer | Coverage and deliberate exclusions below | Canonical resource paths, not technology name counts |
| 3. Add dedicated owners | Package maintainers | Skills, path-scoped instructions and prompts for distinct task families | Per-package resource tests and coverage remaps |
| 4. Add roles | Package maintainers | AI implementer, evaluation reviewer and infrastructure reviewer | Native projection contracts; no pinned models |
| 5. Fit budgets | Maintainer | Shorter descriptions and a split smoke matrix | `agent-kit check`, smoke-matrix role regression |
| 6. Correct setup facts | Documentation | Coverage matrix, counts and verification wording | Documentation and coverage gates |
| 7. Verify | Maintainer | Fresh all-file hooks, full tests, audit and APM smoke | Exact results in the delivery handoff |
| 8. Certify adoption | Consumer/operator | Actual IDE/cloud/model/database evidence | Remains consumer-owned, not claimed by this review |

## Topic coverage and placement

The resource gate reports 79 canonical skills, each with a linked reference and
asset. Structure is necessary, but does not prove provider semantics.

| Requested family | Canonical owner | What is covered / what remains conditional |
| --- | --- | --- |
| SOLID, SRP, dependency injection, ports/adapters, DDD, DRY, KISS, YAGNI | [Hexagonal architecture](../packages/shared/.apm/skills/kit-hexagonal-architecture/SKILL.md), [domain model](../packages/backend/.apm/skills/kit-domain-model/SKILL.md), [refactoring](../packages/shared/.apm/skills/kit-refactor/SKILL.md) | Layer and adapter contracts, value records, invariants, fakes and safe simplification; not an instruction to add a layer to every function |
| Python naming, idioms, types, constants, docstrings, errors, logging, ordering | [Python service](../packages/backend/.apm/skills/kit-python-service/SKILL.md), [consistency](../packages/shared/.apm/skills/kit-consistency/SKILL.md), [documentation](../packages/shared/.apm/skills/kit-documentation/SKILL.md) | Idioms reference, an opt-in redundant-default rule, docstring templates and static checkers; runtime behavior still needs tests |
| FastAPI, DTOs, OpenAPI, status codes, middleware and API compatibility | [FastAPI service](../packages/backend/.apm/skills/kit-fastapi-service/SKILL.md), [API contracts](../packages/backend/.apm/skills/kit-api-contracts/SKILL.md) | App factory, lifespan, dependency injection, middleware order, problem details and health; CORS and rate limiting only when the consumer exposes that surface |
| Authentication and authorization | [API auth](../packages/backend/.apm/skills/kit-auth/SKILL.md), [client auth](../packages/frontend/.apm/skills/kit-client-auth/SKILL.md) | OIDC, JWT/JWKS validation, roles and 401/403 handling; identity provider behavior needs consumer evidence |
| Black-box API testing | [API testing](../packages/backend/.apm/skills/kit-api-testing/SKILL.md) | Postman or Newman, Bruno, `.http` files, Schemathesis and contract tests against a running service |
| Python CLIs and SDK entry points | [CLI tool](../packages/backend/.apm/skills/kit-cli-tool/SKILL.md), [packaging](../packages/backend/.apm/skills/kit-python-package/SKILL.md) | Exit codes, JSON output, configuration precedence and CLI tests |
| Jinja, Polars, Pydantic, schemas and serialization | [Jinja](../packages/backend/.apm/skills/kit-jinja/SKILL.md), [Polars](../packages/backend/.apm/skills/kit-polars-v2/SKILL.md), [Pydantic](../packages/backend/.apm/skills/kit-pydantic-v2/SKILL.md) | Dedicated templates, negative examples and checkers rather than generic framework advice |
| SQL, PostgreSQL, SQLite, migrations, ORM and persistence | [SQL persistence](../packages/backend/.apm/skills/kit-sql-persistence/SKILL.md), [migrations](../packages/backend/.apm/skills/kit-database-migrations/SKILL.md) | SQLAlchemy 2 repositories, unit of work, sessions, transactions and locking. A named database is not an installed driver; run integration tests for the selected backend |
| Neo4j and Cypher | [Graph database](../packages/backend/.apm/skills/kit-graph-database/SKILL.md) | Graph modeling, constraints, indexes and graph repositories; requires a consumer Neo4j instance for integration evidence |
| FAISS, RRF, LightRAG, RAG-Anything, corrective retrieval, LlamaIndex | [Retrieval](../packages/ai/.apm/skills/kit-retrieval/SKILL.md) | Chunking, fusion, metrics, ACL/deletion, bounded corrective loops and measured backend selection |
| LLM clients, managed prompts, gateways and local models | [LLM client](../packages/ai/.apm/skills/kit-llm-client/SKILL.md), [LLM gateway](../packages/ai/.apm/skills/kit-llm-gateway/SKILL.md) | Typed provider boundaries, retry/deadline/cost limits, prompt versions, LiteLLM proxy and Ollama configuration; no model or SaaS calls in tests |
| LLM evaluation and experiments | [LLM evaluation](../packages/ai/.apm/skills/kit-llm-evaluation/SKILL.md), [configuration](../packages/backend/.apm/skills/kit-config/SKILL.md) | Golden datasets, judges, statistics, CI gates and sweeps over model, `prompt_version`, `eval_dataset_version`, temperature and seed. Hydra applies to LLM experiments, not model training. Roles: `kit-ai-engineer`, `kit-eval-reviewer` |
| Agent systems, LangGraph, durable workflows and subagent hierarchies | [Agent systems](../packages/ai/.apm/skills/kit-agent-systems/SKILL.md), [graph workflows](../packages/ai/.apm/skills/kit-langgraph/SKILL.md), [subagent delivery](../packages/shared/.apm/skills/kit-subagent-delivery/SKILL.md), [agent runtime](../packages/shared/.apm/skills/kit-agent-runtime/SKILL.md) | Tool guardrails, budgets, bounded state, owned paths and coordinator verification; CrewAI or fleet engines are optional replacements |
| SSE/WebSocket, async work, Redis, Celery and FIFO delivery | [Server streaming](../packages/ai/.apm/skills/kit-server-streaming/SKILL.md), [task queues](../packages/ai/.apm/skills/kit-task-queue/SKILL.md), [client realtime](../packages/frontend/.apm/skills/kit-client-realtime/SKILL.md) | Ordering, cancellation, backpressure, idempotency and retry contracts. A transport label alone does not guarantee exactly-once processing |
| Configuration and `.env` examples | [Configuration](../packages/backend/.apm/skills/kit-config/SKILL.md), [repository setup](../packages/shared/.apm/skills/kit-repository-setup/SKILL.md) | Settings ownership and bounded experiment inputs; configuration must not become an arbitrary-code execution channel |
| TDD, SDD, unit/property/integration/browser testing, tox and nox | [Test first](../packages/shared/.apm/skills/kit-test-first/SKILL.md), [specification workflow](../packages/workflows/.apm/skills/kit-spec-workflow/SKILL.md), [frontend testing](../packages/frontend/.apm/skills/kit-frontend-testing/SKILL.md) | Test tiers, a test-layout checker, a nox template and negative fixtures; example parsing is not end-to-end execution |
| React, design systems, build tooling and browser evidence | [Frontend features](../packages/frontend/.apm/skills/kit-react-feature/SKILL.md), [design system](../packages/frontend/.apm/skills/kit-design-system/SKILL.md), [frontend build](../packages/frontend/.apm/skills/kit-frontend-build/SKILL.md) | Tokens, Tailwind v4 themes, shadcn/ui theming, Vite and Bun configuration and bundle budgets; no frontend runtime is needed for this CLI |
| Shared names across backend and frontend | [Naming registry](../packages/coordination/.apm/skills/kit-naming-registry/SKILL.md) | One canonical registry for routes, events, enum values and error codes |
| Azure, Terraform, containers and infrastructure review | [Infrastructure review](../packages/iac/.apm/skills/kit-infra-review/SKILL.md), [containers](../packages/iac/.apm/skills/kit-containers/SKILL.md), Azure/Terraform skills | Change-type worksheets and the read-only `kit-infra-reviewer`; preview/plan evidence, not authenticated deployments |
| Reverse proxies, TLS, SSH and server access | [Edge networking](../packages/iac/.apm/skills/kit-edge-networking/SKILL.md), [remote access](../packages/iac/.apm/skills/kit-remote-access/SKILL.md) | nginx, Caddy and Traefik configuration, forwarded headers, `sshd_config` hardening and bastions; production access remains operator-owned |
| Health/readiness, Prometheus, Grafana, traces, metrics and logs | [Observability](../packages/iac/.apm/skills/kit-observability/SKILL.md) | Redaction, cardinality, health semantics and a local collector, Prometheus and Grafana stack template; deploy dashboards only for an actual service |
| VS Code, MCP, Postman, browser and repository tools | [Editor](../packages/shared/.apm/skills/kit-editor/SKILL.md), [MCP integration](../packages/shared/.apm/skills/kit-mcp-integration/SKILL.md), [MCP adoption](mcp-adoption.md) | Native examples, consent, tool permissions, data boundaries and removal. Examples remain inactive in portable bundles |
| CI, pre-commit, security, licensing, update bots and releases | [CI review](../packages/iac/.apm/skills/kit-ci-review/SKILL.md), [verification](../packages/shared/.apm/skills/kit-verify-change/SKILL.md), [supply chain](../packages/shared/.apm/skills/kit-supply-chain/SKILL.md), [secure code](../packages/shared/.apm/skills/kit-secure-code/SKILL.md), [release](../packages/shared/.apm/skills/kit-release/SKILL.md) | Quality-gate catalog, lockfiles, pins, SBOMs and provenance, untrusted-input handling; one update manager is enough unless a documented gap justifies another |
| Whole-repository audit and modernization | [Codebase audit](../packages/workflows/.apm/skills/kit-codebase-audit/SKILL.md), [modernize](../packages/workflows/.apm/skills/kit-modernize/SKILL.md) | Ranked, evidenced findings without fixes; measured, reversible upgrade batches |
| Knowledge, memory, Mermaid, handoffs, feedback loops, context and cost | [Project memory](../packages/shared/.apm/skills/kit-project-memory/SKILL.md), [context engineering](../packages/shared/.apm/skills/kit-context-engineering/SKILL.md), [feedback loop](../packages/shared/.apm/skills/kit-feedback-loop/SKILL.md), [onboarding](../packages/shared/.apm/skills/kit-context-onboarding/SKILL.md), [documentation](../packages/shared/.apm/skills/kit-documentation/SKILL.md) | Consumer-owned facts, decision and lesson records, targeted handoffs, Mermaid diagrams and bounded self-review. Keep optional detail out of always-on instructions |

## What changed

- 25 dedicated skills were added across all seven portable bundles, with
  path-scoped instructions and prompts; the coordination bundle now delivers
  instructions. Existing owners were deepened rather than duplicated.
- Three roles were added: `kit-ai-engineer`, `kit-eval-reviewer` and
  `kit-infra-reviewer`. Role assets no longer pin models, because a host
  rejected an unavailable pinned model instead of falling back.
- The configuration experiment template now models LLM evaluation sweeps; its
  JSON template and typed loader previously disagreed and failed 36 tests.
- 16 skill descriptions were shortened, and the APM smoke matrix was split into
  three selections, so every catalog budget stays unchanged.
- Coverage remaps point original capabilities to their new dedicated owners,
  and three original scripts now map to portable checkers.

Deferred: `apm-cli` 0.35.0 was released on 2026-10-22 and is not adopted yet
because of the 14-day dependency cooldown. Re-evaluate on or after 2026-11-05.

## Systematic review refresh, 2026-10-24

The review combined source inspection, a private local pattern comparison,
independent primary-source research, bounded implementation workers and
regression tests. Local comparison material was not copied or named in portable
content. Existing staged authoring work was retained; this refresh does not
attribute that earlier work to the new changes.

### Plan and implementation owners

| Order | Review/implementation task | Owner | Retained acceptance evidence |
| --- | --- | --- | --- |
| 1 | Inventory existing topics, source owners, budgets and dirty-tree boundaries | Coordinator and planner | Existing 79-skill coverage map; no new discovery entries or raised budgets |
| 2 | Check placement, dependency direction and prior art | Architecture reviewer | Existing evaluation, configuration, container and quality-check owners reused |
| 3 | Refresh official agent/native, context, prompt, evaluation and supply-chain documentation | Research worker and infrastructure worker | [Research refresh](sources.md#behavior-and-standards-refresh-2026-10-24), explicit unavailable/version-sensitive checks |
| 4 | Trace toolkit CLI, validation, selection, provenance, relocation and native-role contracts | Code reviewer and repair worker | Synthetic negative tests plus valid controls for all seven finding families below |
| 5 | Enforce evaluation baseline compatibility and honest numeric gates | Evaluation worker | Fingerprint/scorer identity, complete-report roundtrip, invalid baseline/tolerance and scoring-only controls |
| 6 | Exercise Langfuse experiment callbacks rather than source text alone | Evaluation worker | Fake facade proves approval denial, metadata forwarding, case provenance and error behavior |
| 7 | Add optional DSPy candidate and clarify Hydra experiment scope | Coordinator | Input-only fake program scores through existing harness; invalid outputs/failures remain explicit |
| 8 | Make Trivy image scanning a usable opt-in resource | Infrastructure worker | Immutable image/scanner validation, explicit finding policy, scanner/database failures and evidence tests |
| 9 | Repair portable gate evidence and async iterator contract checks | Coordinator and checker worker | Failed fixer/check attempts retained; compatible async generators accepted without ignoring coroutine mismatches |
| 10 | Audit vulnerable transitive dependencies before installation | Coordinator | Only reported fixed versions resolved; Python and Bun lock audits passed before sync |
| 11 | Review worker changes, integrate and run final gates | Reviewers and coordinator | Focused regressions, source/resource/type/architecture checks, full verification and released APM smoke |

### Toolkit findings addressed

- Reject file-shaped capability roots instead of allowing composition to index
  an incomplete path.
- Reject empty effective profiles before publishing provenance that the toolkit
  itself cannot verify; inheritance-only nonempty profiles remain supported.
- Require complete frontmatter delimiter lines in instructions and prompts.
- Match local resource-link spelling exactly, including directory case, so
  Windows validation cannot approve links that break after Linux delivery.
- Emit ASCII-safe JSON on protocol output, retaining decoded Unicode without
  depending on a redirected Windows terminal's encoding.
- Validate native-role dependency closure within each effective profile, not
  merely the catalog-wide role union.
- Derive session manifest includes from retained resources and preserve
  file-versus-directory include semantics when prompts are omitted.

### Capability findings addressed

Baseline comparison now rejects missing/mismatching dataset fingerprints and
scorer versions. Old metrics-only baselines must be regenerated; malformed,
non-finite, out-of-domain or unknown metrics and invalid regression tolerances
are input errors, not passing runs. No-gate scoring remains supported and does
not imply release approval.

The Langfuse experiment boundary now retains case source/tags and has executable
fake-facade regressions. DSPy remains an optional input-only candidate, not
another evaluation platform or an installed dependency. Hydra is explicitly
configuration for ChatGPT/OpenAI API parameter/evaluation experiments, not
training, inference serving or website automation.

The portable gate no longer uses ephemeral package runners or synchronizes its
Python environment. It records every fixer/check attempt, so a passing checker
cannot erase a failed fixer. Frozen hook environments still need separate
approved provisioning; this is not a network sandbox.

Trivy's starter scans an identified local built image using reviewed scanner
bytes, gates fixable HIGH/CRITICAL findings explicitly and records actual
scanner/database evidence. Existing SBOM/provenance ownership is unchanged.
Offline runner tests are not an actual image scan.

### Deliberate boundaries

The editor task checker retains its permissive consumer contract; a stricter
all-task facade is an optional future change, not a reason to reject legitimate
non-Task editor operations. No global instructions require web research,
delegation, a diagram or a long response for every trivial task. Those mandates
would increase context/cost and can conflict with the requested concise UX.
Research version-sensitive decisions and revisit architecture when evidence
warrants it; do not repeat unchanged inventories indefinitely.

## Context and maintenance rules

Use the smallest relevant skill selection. Load the procedure first, then only
the reference/asset needed for the current task. Do not turn every technology
name into a discovery entry or repeat commands and policies in several owners.
Existing profiles and all catalog budgets remain unchanged.

Use subagents for bounded, independent work with explicit owned paths and stop
conditions. Do not force delegation for a one-file lookup, run concurrent edits
on one file, or treat agreement between models as test evidence. Record exact
commands/results and useful durable decisions, not full chat transcripts.

Read current official documentation for a version-sensitive change. Repeating
web research for an unchanged local fact increases latency and context use
without improving evidence. Review upstream maintenance, compatibility, license,
security posture and removal cost; stars alone are not an approval mechanism.

## Unverified runtime boundaries

The new templates are tested offline with fakes. Langfuse availability, SDK
compatibility, account permissions, real model quality, LiteLLM and Ollama
behavior, Hydra native composition, SQL and Neo4j databases, identity providers,
reverse proxies, SSH hosts, cloud deployment and IDE permission prompts require
separate consumer evidence. Hydra's upstream documentation distinguishes its
1.4 release candidate from the 1.3 legacy line; do not silently install a
prerelease or assume Python compatibility from examples.

No repository is risk-free. Keep hosted protections and approvals in the
[operator checklist](github-setup.md), and actual adoption steps in
[setup completeness](setup-completeness.md).

## Research grounding

- [Agent Skills specification](https://agentskills.io/specification): progressive disclosure and optional resource directories.
- [VS Code skills](https://code.visualstudio.com/docs/copilot/customization/agent-skills): host discovery and on-demand resources.
- [Langfuse prompt management](https://langfuse.com/docs/prompt-management/get-started): versioned retrieval, compilation and caching.
- [Langfuse prompt versions](https://langfuse.com/docs/prompt-management/features/prompt-version-control): versions versus rollout labels.
- [Langfuse masking](https://langfuse.com/docs/observability/features/masking): redact before external telemetry.
- [Hydra](https://github.com/hydra-ecosystem/hydra): current release status and supported configuration approach.
- [Hydra instantiation](https://hydra.cc/docs/advanced/instantiate_objects/overview/): configuration-driven execution boundary.
- [MCP security](https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices): consent, authorization and untrusted data boundaries.
- [GitHub Actions security](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions): dependency trust and workflow permissions.
- [pytest good practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html): import modes and test layout.
