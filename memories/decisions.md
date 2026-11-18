# Decisions

## 2026-11-12: Tiered development loop

- Edit: advisory file-scoped Ruff hook. Iterate: `task check` or one test.
  Commit: file-scoped hooks. Push: repository-wide, pin, duplication and link
  hooks. Handoff and CI: `task verify` (coverage runs here, not locally).
- CI must run `pre-commit run --all-files --hook-stage pre-push` as well, or
  pre-push hooks silently skip CI.
- prek, testmon and a PR-only reduced matrix were considered and deferred: they
  add tools or governance surface without measured need.
- Measured on a 4-core laptop: unit and property took 664 s; `slow` on four
  whole-catalog guard modules (70% of guard time, 4% of guard tests) brings
  `task check` tests to 215 s. Verify and CI still run them.
- Hooks use `uv run --locked --no-sync` (each sync check costs 0.3-1 s and a
  commit must not install); only `dependency-licenses` syncs, after the audit.
- CI `push` covers `main` only; branches verify once through `pull_request`.

## 2026-11-11: Tool configuration stays in dedicated files

- `ruff.toml`, `ty.toml`, `pytest.ini`, `.coveragerc`, `.cz.toml`,
  `.importlinter` and `tox.ini` stay separate, by owner decision. `pyproject.toml`
  holds packaging, dependencies, uv and the build backend only.
- Do not merge tool sections into `pyproject.toml` or delete these files. A
  consolidation attempt was reverted at the owner's request.

## 2026-11-11: Azure-native services first; repository azapi modules before AVM

- On Azure, guidance and application compositions should prefer managed services with Entra-only
  auth (no shared keys or local auth) before self-hosted software: Key Vault
  references, Storage without shared keys, Cosmos DB NoSQL with data-plane
  RBAC, Managed Redis, Service Bus, App Configuration, Monitor/OpenTelemetry,
  AI Search hybrid ranking and Foundry. Container Apps stays the default
  compute; AKS needs a named trigger such as operators, GPUs or a mesh.
- Cosmos DB Gremlin is not provided: its client quickstarts connect with account
  keys. Graphs use NoSQL adjacency or PostgreSQL with
  Apache AGE until evidence justifies a dedicated graph database.
- Delivery modules stay hand-written azapi bodies so Bicep and Terraform send
  the same ARM request and are tested offline without restated defaults. Azure
  Verified Modules, pinned by Renovate, cover resources the kit does not ship.
- These are selection preferences, not a claim that Copier wires every service.
  The selection table is
  [azure-native-services.md](../packages/iac/.apm/skills/kit-infra-review/references/azure-native-services.md).
  Delivery includes an opt-in general blob storage composition; Cosmos DB,
  Service Bus and App Configuration are not provided as compositions.
- Evidence: [delivery inventory](../packages/delivery/README.md),
  [cloud target guidance](../packages/iac/.apm/skills/kit-delivery-pipelines/references/cloud-targets.md)
  and the offline `tests/integration/delivery` module tests.

## 2026-11-06: Lean always-on context; reviewed second pass; checked acronyms

- Stale native profile projections and contradictory reviewer contracts reached
  the gates because agent-facing text duplicated policy and no step required an
  independent review after `task verify`.
- AGENTS.md stays language-neutral; Python rules live once in the path-scoped
  `kit-python` instruction. Growth moves to on-demand skills, not instructions.
- After `task verify`, the read-only `kit-code-reviewer` reviews the diff; read-only
  roles may run focused offline checks but never edit or delegate.
- Every skill description starts with "Use when" and every role description with
  "Use"; descriptions are unique, because they are the routing surface.
- PEP 8 CapWords acronyms are uppercase (`SMTPFactory`); the checker's default
  `acronym-case` rule covers class and type alias names, excluding Id/Db/Io/Os.
- The repository declares no packages; the git guard arrives through the
  user-scope install, and `AGENT_KIT_DIR` lets requested commits reach approval.
- Evidence: [context budget tests](../tests/unit/repo_guards/test_context_budget.py),
  [convention tests](../tests/unit/repo_guards/test_convention_asset.py) and
  `task verify -- profiles`.

## 2026-11-06: Docstrings are proportional; Raises lists only what the body raises

- Reviews kept accepting multi-line Args/Returns on single-input delegators and
  `Raises:` entries that only propagate from callees, because policy text said
  propagated entries were legitimate and the gate checked only missing raises.
- Google §3.8.3, PEP 257 and pydoclint DOC501/DOC502 agree: omit sections the
  signature already conveys; document direct raises, `from` translations and
  re-raises. Ruff DOC501/DOC502 stay off (preview, name-only, no factory or
  contract awareness); the conventions checker owns `docstring-raises-extra`,
  `docstring-one-line` and `docstring-class-sections`.
- Protocol, abstract and stub contracts keep their `Raises:`. Mention an
  essential propagated failure in prose, or raise it in the public method.
- Evidence: [docstring contract tests](../tests/unit/repo_guards/test_docstring_contract.py)
  and `task verify -- conventions` over source, scripts, packages and templates.

## 2026-11-03: Native refresh validates everything but writes only changes

- Replacing an identical attested agent file failed with Windows access denied
  during an explicit refresh. Ownership checks still passed after rollback.
- Keep full path, hash and collision validation before comparing bytes. Refresh
  only changed files and ledger bytes; rollback only the affected paths.
  Do not weaken permissions or add retries to rewrite unchanged output.
- Evidence: two regression cases failed before the repair; all 110
  [projection and rollback tests](../tests/unit/repo_guards/test_native_projection.py)
  passed afterward, followed by a successful explicit refresh.

## 2026-10-20: One uv, parallel CI jobs and an aggregate required check

- `tox-uv` installed a second uv (0.13.x) into the project environment, which
  shadowed the system uv inside `uv run` while CI pinned another release.
  Use `tox-uv-bare` so tox, pre-commit and the CLI share the uv on PATH; the
  lockfile is checked with both the minimum (`required-version`) and CI uv.
- CI runs `verify`, `precommit` and `smoke` as parallel jobs with explicit
  timeouts. `Required toolkit checks` must need every other job, so a new job
  cannot fail without blocking merges; governance tests enforce both rules.
- Evidence: [CI workflow](../.github/workflows/toolkit-ci.yml),
  [governance regressions](../tests/unit/repo_guards/test_governance.py) and
  [toolchain alignment tests](../tests/unit/repo_guards/test_devcontainer.py).

## 2026-10-19: Keep capability resources out of application placement

- APM 0.33.0's optimizer treated skill templates and generated copies as app files,
  repeatedly resolving Windows paths and inserting AGENTS context into skill assets.
  Compose explicit compilation exclusions for the three skill trees, without
  excluding their native installation or changing context/time budgets.
- APM's lifecycle lock is user-wide and based on the home directory. Synthetic
  smoke fixtures isolate HOME, USERPROFILE and APM_HOME; APM_HOME alone does not
  isolate that lock. Concurrent coverage runs also need distinct data-file paths.
- Evidence: [resource regression tests](../tests/unit/repo_guards/test_capability_resources.py),
  [actual smoke boundary](../scripts/apm_smoke.py), and
  [verified native configuration](../docs/sources.md).

## 2026-10-19: Identity coverage is not resource-depth evidence

- A retained skill name could pass the old completeness check after its
  task-specific reference disappeared. Require reachable references/assets
  separately and record implemented script replacements as real contained paths.
- Preserve short discovery metadata and unchanged context budgets; put extensive
  task-specific gates and examples in on-demand resources, not adapter policy.
- Native MCP examples remain inactive and host-shaped. Matching server names
  alone does not establish command, endpoint, transport or tool equivalence.
- Evidence: [coverage regressions](../tests/unit/repo_guards/test_capability_coverage.py),
  [resource regressions](../tests/unit/repo_guards/test_capability_resources.py),
  and the [acceptance walkthrough](../docs/setup-completeness.md).

## 2026-10-10: Hexagonal Architecture is the canonical label

- Describe the toolkit as Hexagonal Architecture (Ports and Adapters), with a
  layered application core; Clean Architecture is a related synthesis sharing
  inward dependency inversion, not an opposing architecture.
- Entity classes, separate inbound Protocols, Unit of Work abstractions, and
  exact layer folders are optional design choices. Policies may be functions
  or data structures; Pydantic/config coupling is an explicit isolation trade-off.
- The skill ID changed without altering selection behavior, dependency rules,
  permissions, or runtime choices.
- Evidence: [architecture glossary](../.agents/knowledge-base/architecture.md),
  session selection regressions, and APM smoke.

## 2026-10-09: Pydantic v2 and Polars 2 stay backend opt-in

- Add version-specific procedures/resources to the backend bundle, with narrow
  matching instructions. Keep Pydantic boundary schemas and Polars frames out of
  domain Core. Test copied templates statically; do not make either library a
  production dependency of the toolkit just to validate examples.
- Evidence: backend profile/session composition and
  `tests/unit/repo_guards/test_data_library_capabilities.py`; official [Pydantic](../docs/sources.md)
  and [Polars](../docs/sources.md) documentation.

## 2026-10-09: Explicit session allowlists, not global runtime switches

- Keep project selection unchanged; `compose --skill` selects procedures for a
  narrow workspace while retaining project instructions/policy and omitting
  native role projections. Missing linked skills fail rather than auto-expand.
- Inspect `.apm/selection.json` for actual delivered IDs and character footprint;
  it is integrity-hashed evidence, not a token/billing estimate or tool sandbox.
- Evidence: [session selection tests](../tests/unit/application/test_session_selection.py),
  [runtime context procedure](../packages/shared/.apm/skills/kit-agent-runtime/references/context.md),
  and `task apm:smoke -- --session`.

## 2026-10-08: Canonical APM source, selected delivery

- APM-first authoring; plugins are optional future exports, not another authored tree.
- Compose selected bundles before vendor discovery; default guidance remains small.
- Separate provider-native metadata from portable workflows.
- Keep legal/provenance review and hosting publication operator-owned.
- Evidence: [catalog](../catalog.json), [policy](../docs/policy.md),
  [architecture](../.agents/knowledge-base/architecture.md).

## 2026-10-08: Advisory hook instead of an incomplete shell filter

- The session hook reports context-entry health only.
- A proposed all-denying tool-hook stub was removed rather than shipped as safety.
- Native approval modes and managed controls remain the authorization boundary.
- Evidence: [native compatibility](../docs/compatibility.md) and session-context tests.

## 2026-10-09: Explicit publication metadata

- The repository coordinate, code owners, and private reporting contacts are
  declared in `.github/maintainers.json` and checked for consistency.
- Release artifacts require exact inventory, licenses, provenance, and checksums.
- Evidence: [governance](../GOVERNANCE.md), [release process](../docs/releasing.md),
  and their negative contract tests.

## 2026-10-09: Completeness is an inventory contract, not a small pilot claim

- The eight-skill starting point was not a complete replacement for the original
  setup. Reusable procedures now have explicit replacements; specialized private
  policy and provider authorization remain consumer-owned.
- Keep one root catalog; agentic-setup indexes it, assets remain skill-contained,
  and guard facades call the canonical implementation.
- Render shared role bodies with native permissions rather than copying one
  provider's frontmatter to another.
- Evidence: [exclusions and disposition](../docs/capability-review.md#exclusions-and-disposition) and its coverage/native tests.

## 2026-10-26: One kit, installed once, improved at its source

- Reusable guidance lives only in this repository. Projects install it at user
  scope and never keep local copies or workarounds; a fix is a reviewed pull
  request here, then `apm update -g`.
- No write-capable MCP server and no paid agentic workflow: the agent's own file
  and `gh` tools already do the work, and a server would bypass the checks.
- Git is allowed here only: commit on request; push, pull request and auto-merge
  after approval of the exact command. Prefix rules and terminal approvals are
  speed bumps; the boundary is hosted.
- The agent uses a write-role machine account (classic `public_repo` token,
  no `workflow` scope; fine-grained tokens cannot act as a collaborator on a
  personal repository). The `main` ruleset keeps code-owner and last-push
  approval, so the owner's review is the human gate. The only bypass is the
  admin role in `pull_request` mode, so the owner can merge their own pull
  requests and nobody can push directly.
- Package manifests keep `dependencies: {}`; consumers name `shared` and each
  profile package, because declaring siblings would relax a strict gate.
- Evidence: [improvement loop](../docs/feedback.md), the native-rule behavior
  tests, and a user-scope install in a throwaway profile.
