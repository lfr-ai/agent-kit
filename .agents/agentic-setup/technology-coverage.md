# Technology coverage

This matrix maps technologies to the capability that owns guidance for them:
the instruction that applies automatically by file pattern (`applyTo`), the
skill an agent loads on demand, and any native role rendered from that bundle.
It was derived from [catalog.json](../../catalog.json) and the package contents
at the time of writing.

The library is being expanded concurrently, so treat this page as a map, not a
count. The authoritative sources are the catalog, each bundle's `.apm/` tree,
and the commands under [Regenerate and verify](#regenerate-and-verify).

## Bundle to profile membership

A bundle reaches every profile that selects it directly or through `extends`
(see [profiles](profiles.md)).

| Bundle | Path | Effective profiles |
| --- | --- | --- |
| toolkit | `.` (root `.apm/`) | toolkit |
| shared | `packages/shared` | every profile |
| backend | `packages/backend` | backend, fullstack, ai |
| frontend | `packages/frontend` | frontend, fullstack |
| coordination | `packages/coordination` | fullstack |
| iac | `packages/iac` | iac |
| workflows | `packages/workflows` | workflows |
| ai | `packages/ai` | ai |

Feature profiles combine with a base profile, for example
`compose fullstack --feature iac`.

## Matrix

Instruction and skill names omit the `.instructions.md` and `SKILL.md`
suffixes. The roles column is a best-fit pointer chosen from each role's
description, and a role is listed only in the section of the bundle whose skill
asset defines it, because that is the bundle that delivers it.

### Cross-cutting (shared bundle)

| Technology or concern | Instruction (`applyTo`) | Skills | Roles |
| --- | --- | --- | --- |
| Safety baseline for all files | `kit-safety` (`**`) | `kit-verify-change` | `kit-security-reviewer` |
| Markdown documentation | `kit-docs` (`**/*.md`) | `kit-documentation` | `kit-docs-writer` |
| Agent configuration (`AGENTS.md`, `CLAUDE.md`, Copilot instructions, `.claude/`, `.apm/`) | `kit-agent-config` | `kit-agent-runtime`, `kit-create-skill` | none |
| Project knowledge (`PROJECT.md`, `projects.md`, `llms.txt`, `memories/`, knowledge base) | `kit-knowledge` | `kit-context-onboarding` | `kit-codebase-researcher` |
| Tests (`test_*.py`, `*_test.py`, `*.test.*`, `*.spec.*`) | `kit-test` | `kit-test-first`, `kit-verify-change` | `kit-test-author` |
| Architecture boundaries | none | `kit-hexagonal-architecture` | `kit-plan-architect`, `kit-solid-review`, `kit-deep-thinking` |
| Planning and cross-file consistency | none | `kit-change-plan`, `kit-consistency`, `kit-parallel-work` | `kit-orchestrator`, `kit-planner`, `kit-code-reviewer` |
| Refactoring and modernization | none | `kit-refactor` | `kit-refactor`, `kit-modernization` |
| Defect diagnosis and repair | none | `kit-test-first` | `kit-debug` |
| Editor assistance and optional MCP | none | `kit-editor` (integration catalog, inactive examples) | none |
| Release readiness | none | `kit-release` | `kit-devops`, `kit-devops-implementer` |

### Backend (backend bundle)

| Technology or concern | Instruction (`applyTo`) | Skills | Roles |
| --- | --- | --- | --- |
| Python services and adapters | `kit-backend`, `kit-python-conventions` (`**/*.py`) | `kit-python-service` | `kit-tdd`, `kit-testing`, `kit-backend-implementer` |
| Python packaging and CLI entry points | `kit-python-conventions` | `kit-python-package` | `kit-backend-implementer` |
| HTTP APIs | `kit-backend` | `kit-api-contracts` | `kit-contract-iac-lint` |
| Application configuration and secrets | `kit-pydantic-v2` (`**/*settings.py`) | `kit-config` | none |
| SQL, repositories, Alembic and migrations | `kit-database` | `kit-database-migrations` | none |
| Domain model | `kit-domain` (`**/domain/**`, `**/core/**`) | `kit-domain-model` | `kit-ddd` |
| Specification-driven design | none | none | `kit-sdd` |
| Pydantic v2 | `kit-pydantic-v2` (DTO, schema, request, response, settings files) | `kit-pydantic-v2` | none |
| Polars 2 | `kit-polars-v2` (polars, dataframe, analytics files) | `kit-polars-v2` | none |
| Jinja templates and prompt files | `kit-prompt-registry` (`**/*prompt*.py`, `**/prompts/**`) | `kit-jinja` | none |

### Frontend (frontend bundle)

| Technology or concern | Instruction (`applyTo`) | Skills | Roles |
| --- | --- | --- | --- |
| TypeScript and JavaScript | `kit-typescript`, `kit-frontend` | `kit-react-feature` | `kit-frontend`, `kit-frontend-implementer` |
| React components | `kit-react` (`**/*.tsx`, `**/*.jsx`) | `kit-react-feature`, `kit-component-library` | `kit-frontend` |
| CSS and SCSS | `kit-css` | `kit-component-library` | none |
| Vite, Vitest, Playwright, `tsconfig`, `package.json` | `kit-frontend-tooling` | `kit-frontend-testing`, `kit-browser-tests` | none |
| Accessibility and UI review | `kit-frontend` | `kit-accessibility`, `kit-ui-review` | none |
| Forms | `kit-frontend` | `kit-forms` | none |
| Routing and URL state | `kit-frontend` | `kit-routing` | none |
| Remote data and client state | `kit-frontend` | `kit-state-data` | none |
| WebSocket and event streams in the browser | `kit-frontend` | `kit-client-realtime` | none |
| Public runtime configuration | `kit-frontend` | `kit-runtime-config` | none |
| Browser defect diagnosis | `kit-frontend` | `kit-browser-debugging` | none |

### Cross-stack (coordination bundle)

| Technology or concern | Instruction | Skills | Roles |
| --- | --- | --- | --- |
| Backend and frontend contract changes | none | `kit-fullstack-workflow` | `kit-fullstack` (coordinator) |

### Infrastructure (iac bundle)

| Technology or concern | Instruction (`applyTo`) | Skills | Roles |
| --- | --- | --- | --- |
| Bicep and ARM, Azure what-if | `kit-bicep`, `kit-iac` | `kit-azure-validation`, `kit-infra-review` | none |
| Terraform plans | `kit-terraform`, `kit-iac` | `kit-terraform-validation`, `kit-infra-review` | none |
| Dockerfile, Containerfile and Compose files | `kit-containers`, `kit-iac` | `kit-containers` | none |
| GitHub Actions and Azure DevOps pipelines | `kit-iac` (`.github/workflows/**`, `.azuredevops/**`) | `kit-ci-review` | none |
| Shell and PowerShell scripts | `kit-shell` | `kit-infra-review` | none |
| OpenTelemetry, Prometheus, Grafana | `kit-observability` | `kit-observability` | none |

Infrastructure delegation roles (`kit-devops`, `kit-devops-implementer`) live in
the shared bundle and are therefore available in every profile. The static
contract reviewer `kit-contract-iac-lint` lives in the backend bundle, so an
iac-only composition does not include it.

### Optional workflows (workflows bundle)

| Technology or concern | Instruction (`applyTo`) | Skills | Roles |
| --- | --- | --- | --- |
| Change specifications (`**/scenario.md`) | `kit-spec` | `kit-spec-workflow` | none |
| Code-graph impact analysis | none | `kit-graph-analysis` | none |
| Duplication review | none | `kit-duplication-review` | none |
| Simplification review | none | `kit-simplify-review` | none |

### AI applications (ai bundle)

| Technology or concern | Instruction (`applyTo`) | Skills | Roles |
| --- | --- | --- | --- |
| Model provider clients | `kit-ai-boundaries` (prompt, agent, retrieval, queue, stream paths) | `kit-llm-client` | none |
| LangGraph workflows | `kit-ai-boundaries` | `kit-langgraph` | none |
| Retrieval pipelines | `kit-ai-boundaries` | `kit-retrieval` | none |
| Background task queues | `kit-ai-boundaries` | `kit-task-queue` | none |
| Server-to-client streaming | `kit-ai-boundaries` | `kit-server-streaming` | none |

The ai profile extends backend, so these build on the backend instructions and roles.

### This repository (toolkit bundle)

| Technology or concern | Instruction (`applyTo`) | Skills |
| --- | --- | --- |
| APM bundles, catalog, profiles, adapters | `kit-authoring` (`.apm/**`, `packages/**`, `catalog.json`, `apm*.yml`, `.github/**`, `.claude/**`) | `kit-capability-authoring`, `kit-config-review` |
| Toolkit Python and tests | `kit-python` (`src/**/*.py`, `tests/**/*.py`) | none |
| Adopting a profile in a repository | none | `kit-apm-adopt` |
| Auditing owned APM output and drift | none | `kit-apm-audit` |

## Known gaps

The matrix has no dedicated capability for these; treat them as consumer-owned
or as candidates for new bundles: non-Python backends, mobile clients, NoSQL
data stores, Kubernetes manifests and Helm, and cloud providers other than Azure
for deployment previews.

## Regenerate and verify

Run these from the repository root. They read source only.

```powershell
# Per-profile skill counts, body lines and description budgets
uv run --locked agent-kit check --root . --json

# Instruction file patterns per bundle
Get-ChildItem packages\*\.apm\instructions\*.md, .apm\instructions\*.md |
  ForEach-Object { "{0}/{1}: {2}" -f $_.Directory.Parent.Parent.Name, $_.Name,
    (Select-String -Path $_.FullName -Pattern '^applyTo:' | Select-Object -First 1).Line }

# Skills and their one-line descriptions
Get-ChildItem packages\*\.apm\skills\*\SKILL.md, .apm\skills\*\SKILL.md |
  ForEach-Object { "{0}: {1}" -f $_.Directory.Name,
    (Select-String -Path $_.FullName -Pattern '^description:' | Select-Object -First 1).Line }

# Native roles per role asset
Get-ChildItem packages, .apm -Recurse -Filter agents.json |
  ForEach-Object { $_.Directory.Parent.Name + ": " +
    (((Get-Content $_.FullName -Raw | ConvertFrom-Json).roles | ForEach-Object id) -join ', ') }

# Linked references, assets and scripts per skill
uv run --locked python -m scripts.check_resources --json

# Original inventory dispositions and resource reachability
uv run --locked python -m scripts.check_coverage
```

To confirm what a profile actually delivers, compose it into a new directory and
inspect `.apm/selection.json` and the rendered agent files:

```powershell
uv run --locked agent-kit compose fullstack --feature iac --output build/coverage-probe
uv run --locked agent-kit provenance --root build/coverage-probe
```

When updating this page, change a row only after the owning instruction, skill
or role exists in source, and keep the bundle-to-profile table consistent with
the catalog.
