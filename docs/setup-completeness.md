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
| Context | Existing description/body/policy budgets remain unchanged; session allowlists retain resources without projecting agents | Catalog and selection checks |
| Instructions | Invariants are path-scoped; consumer facts/knowledge have a distinct owner | Native scope semantics |
| Agents | Every declared role reaches a budget-compliant smoke selection in both native formats; flat native folders, hidden workers and least privilege | Native projection contracts |
| Knowledge/setup | Consumer project/knowledge/adoption/evidence templates and a read-only context check are delivered | Consumer fills actual facts |
| Guards/scripts | Implemented replacements name real files; parser failures have runnable regressions | Explicit accepted input schema |
| MCP | Recorded integrations have native examples, sources, approval and removal steps; delivered servers match the selected manifests | Consumer identity, version and policy review |
| Integrity | Audit precedes regeneration; selected resources retain original bytes and provenance | Pinned APM |
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

## 2. Inspect the library, then select it

Choose a [profile](../README.md#select-capabilities), then load only task-relevant
skills and their linked resources. Inspect resource depth without maintaining a
second inventory:

```powershell
uv run --locked python -m scripts.check_resources
uv run --locked python -m scripts.check_resources --json
uv run agent-kit check --root . --json
```

Expect linked resource presence and Python syntax checks, not semantic
certification. The coverage gate also checks structured-template syntax;
consumer application tests remain necessary.

## 3. Compose a project or a session

```powershell
uv run agent-kit compose fullstack --feature iac --runtime copilot --runtime claude --output build/candidate
uv run agent-kit provenance --root build/candidate
```

Compose into a **new** path; existing destinations fail. Review selection,
provenance and roles before adoption. Unselected sibling packages stay dormant.

For a narrow task:

```powershell
uv run agent-kit compose backend --skill kit-python-service --runtime copilot --output build/session-candidate
```

Session packages omit native roles, prompt facades and MCP, but keep the Git guard.
`.apm/selection.json` records skills, retained instructions and authored character
counts, not token/cache/latency/cost estimates. A subfolder cannot suppress
parent/user/plugin skills, models or tools; use a separate reviewed workspace.

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

## 5. Review agents and native behavior

Selected skill assets own role bodies; composition renders host-specific
frontmatter. The [smoke matrix](../scripts/apm_smoke.py) and composition regression
check both adapters, role coverage and resource bytes without raising budgets.
Unselected stack roles must remain absent. See [native discovery and permissions](editor.md#native-discovery-and-menu).

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
task verify -- coverage
task verify -- roles
task verify
task apm:smoke
task apm:smoke -- --session
```

Audit **before** install or rendering can refresh hashes. After canonical edits,
refresh only owned outputs with the pinned tools, then repeat drift/role checks.
Do not repair evidence by weakening policy or hashes.

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

Keep previous source, manifests, locks and native settings for rollback.
Report exact results, unavailable host/cloud checks and operator steps.
Production certification requires actual intended-host and application evidence.
