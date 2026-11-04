# Capability review and disposition

A source and tooling review, not production or hosted-runtime certification.
This repository is a Python capability library with maintainer scripts;
consumer-specific controls belong in consumer tests. Adoption steps live in
[setup completeness](setup-completeness.md).

## Acceptance criteria

- Extend a canonical owner first. Add a skill only for a distinct task family
  that needs its own procedure, resources and tests.
- Every added resource is reachable, relocatable, syntactically valid and useful
  for a named task. New behavior gets positive and negative tests.
- Keep catalog description, instruction and body budgets unchanged; shorten
  descriptions or split selections instead. New roles use existing permission
  tiers. Provider detail belongs in task-loaded references.
- Keep credentials, local paths, private context and realistic secrets out of
  portable resources. Do not add dependencies, network calls or implicit
  third-party execution to illustrate a tool.
- Run source, resource, conventions, type, test and dependency gates, then the
  released APM smoke. Report unavailable native, model, database and hosted
  checks separately; a manifest or matching server name proves no runtime.

## Ordered work and ownership

| Step | Owner | Deliverable | Evidence |
| --- | --- | --- | --- |
| 1. Baseline | Maintainer | Catalog/resource census, full-hook result | `task verify`, `scripts.check_resources`, hooks |
| 2. Map topics | Maintainer | Coverage and exclusions below | Canonical resource paths |
| 3. Dedicated owners | Package maintainers | Skills, scoped instructions, prompts | Per-package resource tests, coverage remaps |
| 4. Roles | Package maintainers | AI implementer, evaluation and infrastructure reviewers | Native projection contracts; no pinned models |
| 5. Budgets | Maintainer | Shorter descriptions, split smoke matrix | `task verify -- source`, smoke-matrix regression |
| 6. Setup facts | Documentation | Coverage, counts, verification wording | Documentation and coverage gates |
| 7. Verify | Maintainer | Hooks, tests, audit, APM smoke | Exact results in the handoff |
| 8. Certify adoption | Consumer/operator | IDE/cloud/model/database evidence | Consumer-owned, not claimed here |

## Topic coverage and placement

The resource gate reports 79 canonical skills, each with a linked reference and
asset. Structure does not prove provider semantics.

| Requested family | Canonical owner | What is covered / what remains conditional |
| --- | --- | --- |
| SOLID, SRP, dependency injection, ports/adapters, DDD, DRY, KISS, YAGNI | [Hexagonal architecture](../packages/shared/.apm/skills/kit-hexagonal-architecture/SKILL.md), [domain model](../packages/backend/.apm/skills/kit-domain-model/SKILL.md), [refactoring](../packages/shared/.apm/skills/kit-refactor/SKILL.md) | Layer and adapter contracts, value records, invariants, fakes and safe simplification; not a layer for every function |
| Python naming, idioms, types, constants, docstrings, errors, logging, ordering | [Python service](../packages/backend/.apm/skills/kit-python-service/SKILL.md), [consistency](../packages/shared/.apm/skills/kit-consistency/SKILL.md), [documentation](../packages/shared/.apm/skills/kit-documentation/SKILL.md) | Idioms reference, opt-in redundant-default rule, docstring templates and static checkers; runtime behavior needs tests |
| FastAPI, DTOs, OpenAPI, status codes, middleware, API compatibility | [FastAPI service](../packages/backend/.apm/skills/kit-fastapi-service/SKILL.md), [API contracts](../packages/backend/.apm/skills/kit-api-contracts/SKILL.md) | App factory, lifespan, DI, middleware order, problem details, health; CORS and rate limiting only when exposed |
| Authentication and authorization | [API auth](../packages/backend/.apm/skills/kit-auth/SKILL.md), [client auth](../packages/frontend/.apm/skills/kit-client-auth/SKILL.md) | OIDC, JWT/JWKS validation, roles, 401/403; identity provider behavior needs consumer evidence |
| Black-box API testing | [API testing](../packages/backend/.apm/skills/kit-api-testing/SKILL.md) | Postman or Newman, Bruno, `.http` files, Schemathesis, contract tests against a running service |
| Python CLIs and SDK entry points | [CLI tool](../packages/backend/.apm/skills/kit-cli-tool/SKILL.md), [packaging](../packages/backend/.apm/skills/kit-python-package/SKILL.md) | Exit codes, JSON output, configuration precedence, CLI tests |
| Jinja, Polars, Pydantic, schemas, serialization | [Jinja](../packages/backend/.apm/skills/kit-jinja/SKILL.md), [Polars](../packages/backend/.apm/skills/kit-polars-v2/SKILL.md), [Pydantic](../packages/backend/.apm/skills/kit-pydantic-v2/SKILL.md) | Templates, negative examples and checkers |
| SQL, PostgreSQL, SQLite, migrations, ORM, persistence | [SQL persistence](../packages/backend/.apm/skills/kit-sql-persistence/SKILL.md), [migrations](../packages/backend/.apm/skills/kit-database-migrations/SKILL.md) | SQLAlchemy 2 repositories, unit of work, transactions, locking; a named database is not an installed driver |
| Neo4j and Cypher | [Graph database](../packages/backend/.apm/skills/kit-graph-database/SKILL.md) | Modeling, constraints, indexes, repositories; needs a consumer Neo4j instance |
| FAISS, RRF, LightRAG, RAG-Anything, corrective retrieval, LlamaIndex | [Retrieval](../packages/ai/.apm/skills/kit-retrieval/SKILL.md) | Chunking, fusion, metrics, ACL/deletion, bounded corrective loops, measured backend selection |
| LLM clients, managed prompts, gateways, local models | [LLM client](../packages/ai/.apm/skills/kit-llm-client/SKILL.md), [LLM gateway](../packages/ai/.apm/skills/kit-llm-gateway/SKILL.md) | Typed provider boundaries, retry/deadline/cost limits, prompt versions, LiteLLM, Ollama; no model calls in tests |
| LLM evaluation and experiments | [LLM evaluation](../packages/ai/.apm/skills/kit-llm-evaluation/SKILL.md), [configuration](../packages/backend/.apm/skills/kit-config/SKILL.md) | Golden datasets, judges, statistics, CI gates, sweeps over model, `prompt_version`, `eval_dataset_version`, temperature and seed. Hydra is for LLM experiments, not training. Roles: `kit-eval-reviewer` under `kit-orchestrator` |
| Agent systems, LangGraph, durable workflows, subagent hierarchies | [Agent systems](../packages/ai/.apm/skills/kit-agent-systems/SKILL.md), [graph workflows](../packages/ai/.apm/skills/kit-langgraph/SKILL.md), [subagent delivery](../packages/shared/.apm/skills/kit-subagent-delivery/SKILL.md), [agent runtime](../packages/shared/.apm/skills/kit-agent-runtime/SKILL.md) | Tool guardrails, budgets, bounded state, owned paths, coordinator verification |
| SSE/WebSocket, async work, Redis, Celery, FIFO delivery | [Server streaming](../packages/ai/.apm/skills/kit-server-streaming/SKILL.md), [task queues](../packages/ai/.apm/skills/kit-task-queue/SKILL.md), [client realtime](../packages/frontend/.apm/skills/kit-client-realtime/SKILL.md) | Ordering, cancellation, backpressure, idempotency, retry; a transport label does not guarantee exactly-once |
| Configuration and `.env` examples | [Configuration](../packages/backend/.apm/skills/kit-config/SKILL.md), [repository setup](../packages/shared/.apm/skills/kit-repository-setup/SKILL.md) | Settings ownership, bounded experiment inputs; configuration must not execute arbitrary code |
| TDD, SDD, unit/property/integration/browser testing, tox, nox | [Test first](../packages/shared/.apm/skills/kit-test-first/SKILL.md), [specification workflow](../packages/workflows/.apm/skills/kit-spec-workflow/SKILL.md), [frontend testing](../packages/frontend/.apm/skills/kit-frontend-testing/SKILL.md) | Test tiers, layout checker, nox template, negative fixtures |
| React, design systems, build tooling, browser evidence | [Frontend features](../packages/frontend/.apm/skills/kit-react-feature/SKILL.md), [design system](../packages/frontend/.apm/skills/kit-design-system/SKILL.md), [frontend build](../packages/frontend/.apm/skills/kit-frontend-build/SKILL.md) | Tokens, Tailwind v4, shadcn/ui theming, Vite, Bun, bundle budgets |
| Shared names across backend and frontend | [Naming registry](../packages/coordination/.apm/skills/kit-naming-registry/SKILL.md) | One registry for routes, events, enum values, error codes |
| Azure, Terraform, containers, infrastructure review | [Infrastructure review](../packages/iac/.apm/skills/kit-infra-review/SKILL.md), [containers](../packages/iac/.apm/skills/kit-containers/SKILL.md), Azure/Terraform skills | Change worksheets, read-only `kit-infra-reviewer`; plan evidence, not deployments |
| Reverse proxies, TLS, SSH, server access | [Edge networking](../packages/iac/.apm/skills/kit-edge-networking/SKILL.md), [remote access](../packages/remote-access/.apm/skills/kit-remote-access/SKILL.md) | nginx, Caddy, Traefik, forwarded headers, `sshd_config`, bastions; production access is operator-owned |
| Health, Prometheus, Grafana, traces, metrics, logs | [Observability](../packages/iac/.apm/skills/kit-observability/SKILL.md) | Redaction, cardinality, health semantics, local collector stack template |
| VS Code, MCP, Postman, browser, repository tools | [Editor](../packages/shared/.apm/skills/kit-editor/SKILL.md), [MCP integration](../packages/shared/.apm/skills/kit-mcp-integration/SKILL.md), [MCP adoption](mcp-adoption.md) | Native examples, consent, permissions, data boundaries, removal; examples inactive in portable bundles |
| CI, pre-commit, security, licensing, update bots, releases | [CI review](../packages/iac/.apm/skills/kit-ci-review/SKILL.md), [verification](../packages/shared/.apm/skills/kit-verify-change/SKILL.md), [supply chain](../packages/shared/.apm/skills/kit-supply-chain/SKILL.md), [secure code](../packages/shared/.apm/skills/kit-secure-code/SKILL.md), [release](../packages/shared/.apm/skills/kit-release/SKILL.md) | Gate catalog, lockfiles, pins, SBOMs, provenance, untrusted input; one update manager unless a gap justifies another |
| Whole-repository audit and modernization | [Codebase audit](../packages/workflows/.apm/skills/kit-codebase-audit/SKILL.md), [modernize](../packages/workflows/.apm/skills/kit-modernize/SKILL.md) | Ranked findings without fixes; measured, reversible upgrade batches |
| Knowledge, memory, Mermaid, handoffs, feedback loops, context, cost | [Project memory](../packages/shared/.apm/skills/kit-project-memory/SKILL.md), [context engineering](../packages/shared/.apm/skills/kit-context-engineering/SKILL.md), [feedback loop](../packages/shared/.apm/skills/kit-feedback-loop/SKILL.md), [onboarding](../packages/shared/.apm/skills/kit-context-onboarding/SKILL.md), [documentation](../packages/shared/.apm/skills/kit-documentation/SKILL.md) | Consumer-owned facts, decision and lesson records, handoffs, diagrams, bounded self-review |

## Exclusions and disposition

The [coverage manifest](../.agents/agentic-setup/coverage.json) owns each
original capability's replacement or exclusion. Compare an original checkout
with the recorded baseline (identities only, not secrets):

```powershell
uv run --locked python -m scripts.check_coverage --source-root <original-checkout>
```

| Original surface | New owner | Difference |
| --- | --- | --- |
| agentic-setup selection | [Root catalog](../catalog.json) and coverage manifest | One selection schema |
| Reusable skills | Package `.apm/skills/` | Consolidated overlapping workflows |
| Scoped instructions | Package `.apm/instructions/` | Generated native rules with selected scope |
| Agents/subagents | Selected skill role assets | Shared bodies, per-host permissions |
| Static guard | Installed validation plus `.agents/guard/` facade | No duplicate guard implementation |
| Editor commands | Task wrappers and editor assets | No application commands or personal shortcuts |
| MCP | [Native manifests and package `apm.yml`](mcp-adoption.md) | Reviewed, optional startup, no committed credentials |
| Hooks | Advisory session health plus the `shared` Git guard | No universal shell sandbox |
| Project facts/knowledge | Consumer | Not copied |

Consolidations:

- OpenSpec maps to one lifecycle workflow; graph procedures to one
  impact/context workflow; Ponytail to original simplification/debt guidance.
  Attribution and licenses are kept; upstream bodies are not redistributed.
- `kit-testing` merges into `kit-test-author`; `kit-tdd` into `kit-test-first`
  plus `kit-test-author`; `kit-fullstack`, `kit-frontend` and `kit-ai-engineer`
  into `kit-orchestrator`. Only selected-stack roles ship;
  [native permissions](editor.md#native-discovery-and-menu) keep workers hidden.
- Pydantic v2 and Polars 2 are backend-only and opt-in, outside domain Core.

Excluded from portable scope: Copier scaffolding, company pipeline IDs, medical
publication, application facts, migrations, deployment identities, license
policy and app DI/port/migration guards (until a tested portable validator
exists). Terraform/Azure what-if reviewers never authorize apply. Identity
mapping is not resource depth; see the
[resource-depth refresh](sources.md#resource-depth-refresh-2026-10-19) and the
[acceptance plan](setup-completeness.md#1-acceptance-plan).

## What changed

- 25 dedicated skills across all seven portable bundles, with scoped
  instructions and prompts; existing owners were deepened, not duplicated.
- Three roles: `kit-ai-engineer`, `kit-eval-reviewer`, `kit-infra-reviewer`.
  Role assets no longer pin models: a host rejected an unavailable pinned model.
- The configuration experiment template models LLM evaluation sweeps; its JSON
  template and typed loader previously disagreed and failed 36 tests.
- 16 descriptions were shortened and the smoke matrix split into three
  selections, so every budget stays unchanged.
- Coverage remaps point originals at their new owners; three original scripts
  map to portable checkers.

The APM upgrade deferral is recorded in [sources](sources.md#pins).

## Systematic review refresh, 2026-10-24

Source inspection, a private local comparison (not copied or named), primary
research, bounded workers and regression tests.

| Order | Task | Owner | Evidence |
| --- | --- | --- | --- |
| 1 | Inventory topics, owners, budgets, dirty-tree boundaries | Coordinator, planner | 79-skill map; no new entries or budgets |
| 2 | Placement, dependency direction, prior art | Architecture reviewer | Existing owners reused |
| 3 | Refresh agent, context, prompt, evaluation, supply-chain docs | Research and infrastructure workers | [Research refresh](sources.md#behavior-and-standards-refresh-2026-10-24) |
| 4 | Trace CLI, validation, selection, provenance, relocation, roles | Code reviewer, repair worker | Negative tests plus valid controls |
| 5 | Evaluation baseline compatibility and numeric gates | Evaluation worker | Fingerprint/scorer identity, invalid-baseline controls |
| 6 | Langfuse experiment callbacks | Evaluation worker | Fake facade: approval denial, metadata, provenance, errors |
| 7 | Optional DSPy candidate, Hydra scope | Coordinator | Input-only fake program through the existing harness |
| 8 | Trivy image scanning opt-in | Infrastructure worker | Immutable image/scanner validation, finding policy |
| 9 | Portable gate evidence, async iterator checks | Coordinator, checker worker | Failed attempts retained; coroutine mismatches rejected |
| 10 | Vulnerable transitive dependencies | Coordinator | Fixed versions only; audits passed before sync |
| 11 | Integrate and run final gates | Reviewers, coordinator | Full verification and APM smoke |

Toolkit findings fixed:

- Reject file-shaped capability roots and empty effective profiles.
- Require complete frontmatter delimiter lines in instructions and prompts.
- Match resource-link spelling exactly, including directory case.
- Emit ASCII-safe JSON regardless of the Windows terminal encoding.
- Validate native-role dependency closure per effective profile.
- Derive session includes from retained resources, preserving file/directory semantics.

Capability findings fixed:

- Baselines reject missing or mismatched dataset fingerprints and scorer
  versions; malformed metrics and invalid tolerances are input errors.
  No-gate scoring remains and does not imply release approval.
- Langfuse experiments keep case source/tags with executable fake regressions.
  DSPy is an optional input-only candidate; Hydra is configuration for API
  evaluation experiments, not training or serving.
- The portable gate records every fixer/check attempt, uses no ephemeral package
  runners and never syncs its environment. It is not a network sandbox.
- Trivy scans an identified local image with reviewed scanner bytes and gates
  fixable HIGH/CRITICAL findings. Offline tests are not an image scan.

Boundaries kept: the editor task checker stays permissive for non-Task
operations, and no global instruction mandates research, delegation, diagrams
or long answers for trivial tasks.

## Unverified runtime boundaries

Templates are tested offline with fakes. Langfuse, SDK compatibility, model
quality, LiteLLM, Ollama, Hydra composition, SQL and Neo4j, identity providers,
reverse proxies, SSH, cloud deployment and IDE prompts need consumer evidence.
Hydra 1.4 is a release candidate; do not install a prerelease silently.
Hosted protections are in the [operator checklist](github-setup.md).

## Research grounding

- [Agent Skills specification](https://agentskills.io/specification): progressive disclosure.
- [VS Code skills](https://code.visualstudio.com/docs/copilot/customization/agent-skills): discovery and on-demand resources.
- [Langfuse prompt management](https://langfuse.com/docs/prompt-management/get-started), [versions](https://langfuse.com/docs/prompt-management/features/prompt-version-control), [masking](https://langfuse.com/docs/observability/features/masking).
- [Hydra](https://github.com/hydra-ecosystem/hydra) and [instantiation](https://hydra.cc/docs/advanced/instantiate_objects/overview/).
- [MCP security](https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices).
- [GitHub Actions security](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions).
- [pytest good practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html).

Further dated sources are in [sources](sources.md).
