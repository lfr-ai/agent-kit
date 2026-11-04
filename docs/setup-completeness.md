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
| Native roles | Repository-owned roles keep their native projections; consumer profile packages do not currently deliver roles | Native projection contracts and explicit limitation |
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

`backend` groups `shared` and `backend`; the consumer needs one package
reference. APM does not read Agent Kit's `catalog.json`; the source repository
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
0.33.0 install path.

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

Consumer APM profile packages currently deliver APM primitives but not native
agent-role files. Role metadata remains authored in skill assets and is
rendered for this repository's own Copilot and Claude projections. Do not infer
consumer role support from those generated source-repository files. The
[APM smoke matrix](../scripts/apm_smoke.py) verifies package installation,
compilation and resources. See
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
profile manifests. The APM smoke exercises source-package installation and
compilation in disposable projects; it does not certify consumer-to-meta-package
dependency resolution.

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
