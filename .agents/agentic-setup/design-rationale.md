# Design rationale

This document explains why Agent Kit is shaped the way it is: what each design
choice protects, what it costs, and which alternatives were rejected. Every
statement is grounded in the current source; follow the links to the owning code
or document before relying on a detail. Dated decision records live in
[memories/decisions.md](../../memories/decisions.md) and are indexed in
[design decisions](../knowledge-base/design-decisions.md).

## Summary

| Choice | Protects | Main cost |
| --- | --- | --- |
| APM-first canonical source | One authored copy per capability | Depends on a pinned external CLI |
| Selected delivery (profiles, features, sessions) | Small default context, no dormant capabilities | Consumers must choose explicitly |
| Catalog budgets | Bounded discovery metadata and policy size | Detail must move into on-demand resources |
| Provenance hashes | Detectable drift and unrecorded files | Not a signature or authorization |
| Advisory session hook | Honest context-entry health signal | No tool filtering is provided |
| Opt-in MCP | No implicit server startup or credentials | Manual review per integration |
| Rendered native roles | Shared role bodies with host-correct permissions | Needs a renderer and an ownership ledger |
| Atomic, non-replacing output | Consumers and sources are never overwritten | Output path must be new |

## APM-first canonical source

Capabilities are authored once as APM primitives under `.apm/` (this
repository's own governance) and `packages/*/.apm/` (portable bundles). Each
bundle has its own `apm.yml` with explicit `includes`, no dependencies and no
executables. Runtime discovery directories such as `.agents/skills/`,
`.claude/skills/` and `.github/instructions/` are delivery output, not authored
source.

Why:

- A single source removes divergence between Copilot and Claude copies of the
  same procedure; host differences are confined to native metadata.
- APM already installs skills, instructions and lockfile ledgers for both
  targets, so the toolkit does not reimplement installation.
- The pinned `apm-cli==0.33.0` development dependency makes the boundary
  reproducible; [apm_adapter.py](../../src/agent_kit/infrastructure/apm_adapter.py)
  refuses any other installed version.

Rejected alternatives:

- **Authoring native plugins directly.** Plugins remain optional future exports
  rather than a second authored tree ([decision 2026-10-08](../../memories/decisions.md)).
- **Hand-maintained per-host copies.** They drift silently and double review cost.
- **Trusting APM's own policy discovery at install time.** APM 0.33.0 does not
  automatically select every project-local policy file, so the toolkit validates
  policy before composing and runs explicit policy/audit commands
  ([policy](../../docs/policy.md)).

Trade-off: an APM release change can alter behavior. The smoke gate
([apm_smoke.py](../../scripts/apm_smoke.py)) exercises the real CLI in a
disposable package with an isolated home so regressions surface before adoption.

## Selected delivery

[catalog.json](../../catalog.json) is the only source of profile and bundle
selection. A profile lists bundles and may `extend` other profiles; `--feature`
adds further profiles. Resolution is an ordered, de-duplicated union computed by
`_effective_bundles` in
[catalog_service.py](../../src/agent_kit/application/services/catalog_service.py).
Composition copies only the selected bundles into a new package before APM runs,
so recursive APM discovery cannot activate dormant sibling packages.

`compose --skill` narrows a project selection to an explicit session allowlist:

- Only named skills are delivered; unknown or unavailable IDs fail.
- General project instructions and policy are retained; an instruction whose
  name matches an available but unselected skill is omitted.
- If a retained document links to an omitted resource, composition fails and
  asks for the owning skill to be added explicitly instead of auto-expanding.
- Native role projections are omitted.
- `.apm/selection.json` records the mode, skill and instruction IDs, authored
  character counts and the number of native role files.

Why: large always-on libraries dilute agent attention and expose irrelevant
tools. Explicit selection keeps the default small and auditable.

Rejected alternatives:

- **Global runtime switches** that toggle capabilities after installation. They
  cannot hide parent, user or plugin capabilities, so they would overstate
  isolation ([decision 2026-10-09](../../memories/decisions.md)).
- **Automatic expansion of linked skills.** It would silently grow a session
  beyond what the operator selected.
- **Token or cost estimates in the selection report.** Character counts are
  measurable; billed tokens depend on the host and model.

## Budgets

The catalog declares four budgets, validated by `agent-kit check`:

| Budget | Applies to |
| --- | --- |
| `policy_lines` | Lines in the root `AGENTS.md` policy |
| `skill_body_lines` | Body lines of each `SKILL.md` |
| `description_chars` | Each skill description |
| `profile_description_chars` | Sum of descriptions in every declared profile, and in each composed selection |

Native role assets have separate fixed limits in
[native_delivery.py](../../src/agent_kit/application/services/native_delivery.py)
(single-line description up to 180 characters, body up to 125 lines).

Why: descriptions are loaded for discovery in every session, so their total is
the real always-on cost. Procedures stay short; task detail lives in linked
`references/` and `assets/` that agents open on demand.

Trade-off: authors must split content and keep links reachable. The resource
gate ([check_resources.py](../../scripts/check_resources.py)) rejects
checklist-only or unreachable resources so the split cannot hide missing depth.

Rejected alternative: **raising budgets to fit new content.** Decisions record
that context and time budgets stay unchanged; content moves to resources instead.

## Provenance

Composition writes `provenance.json` with the catalog version, profile, selected
bundle names and paths, and a SHA-256 hash for every planned file.
`agent-kit provenance` ([provenance_service.py](../../src/agent_kit/application/services/provenance_service.py))
then reports missing, extra and altered files. After APM installation it also
accepts only first-party deployments recorded in `apm.lock.yaml` under the
known delivery roots, comparing their content hashes with the installed bytes.

Why: drift must be detectable **before** any regeneration replaces the
evidence. The drift ordering in [migration](../../docs/migration.md) and
[verification](../../docs/verification.md) depends on this.

Limits, stated explicitly:

- Provenance is an integrity record, not a signature or an authorization grant.
- Compiled root context, the APM lock and ignore files are not source-provenance
  bytes; inspect them separately and run the explicit APM audit.
- Release artifacts are additionally compared with a fresh composition from the
  trusted checkout by [check_release.py](../../scripts/check_release.py).

Rejected alternative: **fabricating a release lock or refreshing hashes to make
a check pass.** Policy forbids weakening hashes; drift is reported, not repaired.

## Strict APM policy

[apm-policy.yml](../../apm-policy.yml) blocks by default: no dependency or MCP
allow-list entries, self-defined MCP denied, lifecycle scripts and executables
denied, explicit includes and integrity hashes required, and audit fails on
drift. The toolkit rejects unknown policy keys, including nested ones. The
controlled APM process always runs with `APM_NO_SCRIPTS=1` and
`APM_NON_INTERACTIVE=1`.

Trade-off: enabling a dependency later requires an exact approved source,
reviewed executables, allow-list entries and a retained negative test.

## Advisory session hook

Both hosts run `uv run --locked agent-kit context` at session start
(`.claude/settings.json`, `.github/hooks/session-context.json`). The command
reads bounded JSON from standard input, reports the workspace and any missing
entry files (`AGENTS.md`, `PROJECT.md`, `llms.txt`), and returns additional
context. [check_native.py](../../scripts/check_native.py) pins this contract.

Why: a hook that only reports health is honest about what it does.

Rejected alternative: **an all-denying tool-hook stub.** It was removed rather
than shipped as apparent safety ([decision 2026-10-08](../../memories/decisions.md)).
Native approval modes, least-privilege identities and managed controls remain
the authorization boundary ([compatibility](../../docs/compatibility.md)).

## Opt-in MCP

The active MCP manifest is empty and the policy allow-list is empty. The editor
capability (`kit-editor`) carries an integration catalog plus inactive VS Code
(`servers`) and Claude (`mcpServers`) example wrappers with reviewed-version
placeholders. Composition, resource checks and smoke never start a server.

Why: MCP servers execute code with the user's permissions, need credentials and
add tool context. Enabling one is a reviewed consumer decision.

Rejected alternative: **enabling every example to match server names.** A
matching name does not establish command, endpoint, transport or tool
equivalence ([decision 2026-10-19](../../memories/decisions.md)).

## Native role rendering

Agent roles are authored once as JSON assets inside skills
(`.apm/skills/<skill>/assets/agents.json`) with a closed schema: `id`, `kind`
(`primary` or `worker`), `tier` (`readonly`, `implementer` or `coordinator`),
`description`, `body`, `workers` and optional `models`. The renderer emits:

- Copilot files under `.github/agents/` (workers in `subagents/`) with `tools`,
  `agents`, `user-invocable` and `disable-model-invocation` metadata.
- Claude files under `.claude/agents/` (workers in `subagents/`) with a `tools`
  string; coordinators receive `Agent(<workers>)`.
- The identical role body for both hosts.

Tier maps to bounded tools: read-only roles get read/search only; implementers
add edit and execute; coordinators may delegate only to declared worker IDs,
which must exist and be workers.

Because roles live in skills, a profile delivers only the roles of its selected
bundles. A frontend-only package does not silently receive backend implementers.
Session packages omit roles entirely.

This repository's own projections are selected by
[self.json](self.json) and recorded in [native-lock.json](native-lock.json).
[render_native.py](../../scripts/render_native.py) checks them by default and
only rewrites them with `--write`, refusing to overwrite independently edited
or unowned files and rolling back on failure.

Rejected alternatives:

- **Copying one provider's frontmatter to another.** Tool names, delegation and
  visibility flags have no exact cross-host equivalents.
- **Relying on APM's cross-provider agent conversion.** Role files are
  toolkit-authored projections included in source provenance.

## Atomic, non-replacing output

[output_adapter.py](../../src/agent_kit/infrastructure/output_adapter.py)
writes into a sibling staging directory and publishes with a no-replace rename
(`renameat2` on Linux, `rename` on Windows). It rejects existing destinations,
symlinks or junctions in the path, case-insensitive collisions, the source root
or its ancestors, overlaps with any bundle, and output inside the source root
other than beneath `build/`. Other platforms fail explicitly.

Rejected alternative: **overwriting or merging into a consumer repository.**
Adoption is a reviewed transfer from a candidate package ([migration](../../docs/migration.md)).

## Layering

The implementation follows Hexagonal Architecture with a layered core; see
[architecture](../knowledge-base/architecture.md). Core is stdlib-only and never
reads files or runs APM; Application validates and plans; Infrastructure owns
files and processes; Presentation owns the CLI; Composition wires them.
