# Complete setup: plan and adoption walkthrough

This guide is for maintainers selecting and adopting the toolkit in a real
repository. Its outcome is a reviewed candidate with explicit consumer work,
not a claim that generated configuration certifies production behavior.
The [capability review](capability-review.md) maps requested topics to existing
owners, documented extensions and consumer verification work.

## 1. Acceptance plan

| Work item | Acceptance evidence | Prerequisite |
| --- | --- | --- |
| Inventory | Every recorded skill, instruction, role, prompt, script, integration, hook and asset category has a disposition | Recorded source baseline |
| Resource depth | Every canonical skill has a reachable nonempty reference and usable asset; guides give concrete failure cases and gates | Owning audience and prior art |
| Context | Existing description/body/policy budgets remain unchanged; session allowlists retain resources without projecting agents | Catalog and selection checks |
| Instructions | Invariants are path-scoped; consumer facts/knowledge have a distinct owner | Native scope semantics |
| Agents | All 27 declared roles (the 24 recorded originals plus three added) reach at least one budget-compliant smoke selection in both native formats; workers retain least privilege | Native projection contracts |
| Knowledge/setup | Consumer project/knowledge/adoption/evidence templates and a read-only context check are delivered | Consumer fills actual facts |
| Guards/scripts | Implemented replacements name real files; parser failures have runnable regressions | Explicit accepted input schema |
| MCP | All 11 integrations have native examples, sources, approval criteria and removal steps; portable defaults stay inactive | Consumer identity, version and policy review |
| Integrity | Audit precedes regeneration; selected resources retain original bytes and provenance | Pinned APM |
| Open-source delivery | Community, ownership, workflow, release and publication checks are executable | Operator configures hosted controls |
| Handoff | Full verification and actual APM smoke run after changes; limitations are reported separately | Integrated source |

The original inventory contained 74 skills, 31 instructions, 24 roles, 24 prompt
facades, 22 scripts, 11 integrations, five asset categories and three hooks.
The current source contains 79 skills, 51 instructions, 27 roles and 41 prompt
files. Consolidation intentionally does not create a duplicate discovery entry
for each original capability. The
[coverage mapping](../.agents/agentic-setup/coverage.json) records original
identities and is authoritative for replacements and exclusions; current
package counts are summarized in the [research index](sources.md).

### Runtime limitation

Static inventory and policy checks do not certify behavior in a native editor
session. MCP discovery, authentication, approval prompts, and live tool behavior
must be checked in the intended host; verification does not start or authenticate
MCP servers.

## 2. Inspect the library, then select it

The canonical library has 79 skills, split by ownership:

| Bundle | Skills | Resource emphasis |
| --- | --- | --- |
| toolkit | 4 | Adoption, audit, capability authoring, configuration review |
| shared | 21 | Context, project memory, feedback loops, planning, subagent delivery, architecture, consistency, tests, agents, editor/MCP, documentation, refactoring, secure code, supply chain, repository setup and release |
| backend | 15 | Service/conventions, FastAPI, auth, contracts, API tests, CLI tools, configuration, SQL persistence, graph databases, migrations, domain, Jinja, data libraries and packaging |
| frontend | 15 | Components, design system, build tooling, client auth, accessibility, browser evidence/tests, forms, routing, state, realtime and public configuration |
| coordination | 2 | Cross-stack contract, journey and rollout; shared naming registry |
| iac | 8 | Infrastructure evidence, Azure what-if, Terraform plan, CI, containers, observability, edge networking and remote access |
| workflows | 6 | Specification lifecycle, graph impact, duplication, simplification, codebase audit and modernization |
| ai | 8 | Retrieval, model clients, gateways, evaluation, agent systems, graph execution, streaming and queues |

Do not load this whole library into every session. Descriptions select a skill;
its short procedure selects task-specific references, assets and checks.
The complete resource census is executable rather than a second hand-maintained
list of file names:

```powershell
uv run --locked python -m scripts.check_resources
uv run --locked python -m scripts.check_resources --json
uv run agent-kit check --root . --json
```

The census proves linked resource presence and Python syntax, not semantic
completeness. Domain guides and their owning application tests remain necessary.
Structured templates receive syntax checks through the coverage gate.

## 3. Compose a project or a session

```powershell
uv run agent-kit compose fullstack --feature iac --runtime copilot --runtime claude --output build/candidate
uv run agent-kit provenance --root build/candidate
```

Compose into a **new** output path. Review selection, source provenance and native
roles before adoption. Profiles compose a selected union; dormant sibling
packages do not become active simply because they exist in the library.

For a narrow task:

```powershell
uv run agent-kit compose backend --skill kit-python-service --runtime copilot --output build/session-candidate
```

Session packages omit native role projections. Their selection report records
authored character counts and retained instructions; it is not a token, cache,
latency or cost estimate. Repository selection cannot suppress parent/user/plugin
skills, models or tools.

### A comprehensive improvement entry point

Select the `workflows` bundle to obtain
[`kit-improve-codebase`](../packages/workflows/.apm/prompts/kit-improve-codebase.prompt.md).
It combines read-only discovery with requested cleanup, modernization,
refactoring and simplification, without changing the read-only audit facade.
Provide the scope, goals and constraints; the prompt requires convention gates,
behavior protection, readable/simple designs and evidence-backed completion.
The existing shared safety rule carries the simplicity/context invariant across
file types; the scoped readability rule requires applicable convention checks.
On-demand references cover
[central ownership, filenames and subfolder decisions](../packages/shared/.apm/skills/kit-consistency/references/module-layout.md)
and [Python partial/decorator contracts](../packages/backend/.apm/skills/kit-python-service/references/callables-and-decorators.md).
Use the existing narrower audit, refactor, consistency or modernization prompts
when an end-to-end pass would be excessive.

VS Code documents prompt files as manually invoked workflows in its Local
harness. After delivery to that host, select the prompt as a slash command or
with **Chat: Run Prompt**. Other harnesses need their own discovery/invocation
check; file delivery does not certify model compliance or native permissions.
Instructions guide behavior; the consumer's actual tests, lint, type,
architecture and naming checks enforce the machine-checkable conventions.
Readability and cognitive load also require review, not an invented token or
production-readiness score.

## 4. Fill consumer context and wire its gates

Use the delivered onboarding project-facts and knowledge-index templates, plus
the adoption record. Record actual commands, cwd, supported versions, source
owners, architecture, error behavior, decisions and recovery. Do not copy this
toolkit's facts or private material from another repository.

The portable context checker accepts `--root <consumer>` and repeated `--entry`
paths. Its default entries are the repository policy, project facts and agent
index. It rejects missing/empty files and broken or escaping local links.
It does not validate factual accuracy, external links, Markdown anchors, domain
invariants, dependency licenses or DI wiring.

Run its `--self-test` first, then add the explicit checker invocation to the
consumer's existing runner. Keep behavioral, architecture, migration, license
and integration gates in the consumer. Do not replace them with toolkit metadata
checks or create another giant independently maintained guard.

## 5. Review agents and native behavior

Role source lives in selected skill assets; composition renders separate native
frontmatter from shared bodies. The smoke-matrix regression composes each of the
three smoke selections (`fullstack`; `ai` with `iac`; `workflows`), checks that
every one of the 27 declared roles reaches at least one of them in both adapters,
and verifies resource bytes survive selection. A single selection of every
bundle would exceed the profile description budget, so the matrix splits the
work instead of raising the budget.
Stack-specific absence is intentional; a frontend-only delivery should not
silently receive backend implementers.

Use the runtime certification worksheet to test actual discovery, selected and
unselected capabilities, read-only edit/shell/delegation denials, bounded
implementation, hook events/cwd and duplicate execution.
Toolkit roles do not pin models; they inherit the caller's model because a
host may reject an unavailable pinned model instead of falling back. A consumer
that adds model preferences must certify them in each host and account.

The advisory session hook reports context-entry health. It is not a universal
tool guardian. Native permission policy remains authoritative; command hooks
can execute with the user's permissions. License enforcement belongs before
dependency adoption/publication, not a post-action notification.

## 6. Adopt optional MCP deliberately

MCP is **not omitted from the library**: all 11 recorded integrations have
native examples and task-specific adoption criteria in the editor capability.
Portable packages keep them inactive. This workspace separately configures three
remote servers as described in [MCP adoption](mcp-adoption.md); auto-start remains
disabled. Neither examples nor native manifests establish authorization or prove
a successful connection.

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

Templates are not connection tests. A registry listing is not security vetting.
GitNexus license suitability, browser-session isolation, cloud subscription
identity and Postman regional/workspace requirements need explicit review.
Do not enable all examples just to obtain matching server names.

## 7. Validate and refresh owned output

```powershell
task verify -- drift
task verify -- source
task verify -- coverage
task verify -- roles
task verify
task apm:smoke
task apm:smoke -- --session
```

The first audit must happen **before** install or role rendering refreshes
ownership hashes. After canonical changes, refresh only their owning outputs
with the pinned toolchain, then repeat drift and role checks.
The completion gate is check-only; formatting remains an explicit operation.
The [systematic review refresh](capability-review.md#systematic-review-refresh-2026-10-24)
adds executable baseline identity, export approval, input-only candidate,
container scan, gate-attempt and async-iterator checks. These supplement resource
presence and syntax checks rather than replacing consumer integration tests.
The default APM smoke covers fullstack with IaC, workflows and AI in a disposable
package. Its temporary home isolates APM's user-wide lifecycle lock/cache.
Composition excludes skill source/delivery trees from compilation's application
placement scan, not from installation or native discovery. Both rosters and
source/installed resource bytes are checked, including unexpected files.
Session smoke separately verifies the narrow backend allowlist.
Compilation runs once per native host so provider-specific instruction
deduplication is preserved instead of assuming mixed-target semantics are identical.

Resource checker regressions include missing and unreachable resources, malformed
Python, native MCP wrapper/inventory disagreement and nonexistent script
replacements. Trusted portable scripts keep runnable self-checks in the test
suite. Consumer code and MCP servers are not executed by resource inspection.

## 8. Finish hosted readiness through the operator

Use the existing [GitHub checklist](github-setup.md) and
[release contract](releasing.md). Repository initialization, remote creation,
branch/ruleset enforcement, independent maintainers, secret scanning, private
reporting, protected release identity and publication require operator work.
Local governance files cannot enable or certify those controls.

Keep previous source, manifest, lock and native settings for rollback.
Report exact commands/results, unavailable native/cloud checks and remaining
operator steps. Only call the setup production-certified after the intended
hosts and consumer application behavior have actually been exercised.
