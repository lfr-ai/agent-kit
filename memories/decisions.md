# Decisions

## 2026-10-20: One uv, parallel CI jobs and an aggregate required check

- `tox-uv` installed a second uv (0.13.x) into the project environment, which
  shadowed the system uv inside `uv run` while CI pinned another release.
  Use `tox-uv-bare` so tox, pre-commit and the CLI share the uv on PATH; the
  lockfile is checked with both the minimum (`required-version`) and CI uv.
- CI runs `verify`, `precommit` and `smoke` as parallel jobs with explicit
  timeouts. `Required toolkit checks` must need every other job, so a new job
  cannot fail without blocking merges; governance tests enforce both rules.
- Evidence: [CI workflow](../.github/workflows/ci.yml),
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
- Evidence: [setup review](../docs/setup-review.md) and its coverage/native tests.
