# Changelog

## Unreleased

### Added

- Updated transitive GitPython to 3.2.1 in `uv.lock` to resolve CVE-2026-114145.
- Dependency supply-chain controls: an audit-first `task bootstrap`, a hashed
  lockfile vulnerability and wheel-only audit, a reviewed license policy, a
  required and scheduled dependency-audit workflow, strict dependency review,
  frozen pre-commit hooks, a digest-pinned link-check image, zizmor workflow
  linting, and Dependabot coverage for dev container features.
- Native agent limits on ad-hoc package installs (Claude Code deny rules and
  VS Code approval rules) plus a portable `dependency-install` tool-guard rule.
- Enforced version pinning: exact development, audit, tox and build-backend
  pins; a Bun-locked jscpd instead of a runtime `bunx`; a digest-pinned dev
  container image with exact feature versions; pinned workflow tool installers;
  and the portable `check_pins.py` gate in `task verify`, pre-commit and APM.
- Named-constant enforcement: an opt-in `magic-number` rule in the portable
  `check_python.py` gate, applied to source, scripts, and APM assets.
- Ruff aligned with the shared strict profile: complexity 6, branch, return, and
  statement limits, `TC` imports, import conventions, and `ASYNC`, `BLE`, `EM`,
  `EXE`, `FLY`, `PYI`, `T10` and `YTT` rules.
- pytest `strict = true`, an actionlint hook with a pinned Go toolchain, and both
  workflow linters in the portable pre-commit template.
- Minimal zizmor configuration for this repository and APM consumers;
  scanner-config edits rerun workflow analysis. Enabled hosted grammar checks,
  extended required ty checks to portable Python assets, and documented
  native/hosted discovery.
- A 14-day Dependabot version-update cooldown across repository ecosystems and
  portable templates, enforced by zizmor with no shorter semantic-version
  overrides. Security updates remain exempt.
- Locale-independent APM subprocess output handling prevents Windows CP1252
  decoding failures. A bounded five-minute per-command audit window accommodates
  cold full-profile replay without skipping policy or integrity checks.
- Kept actionlint's narrow self-repository compatibility exception in hook
  arguments instead of a separate configuration file.
- Source composition omits interpreter bytecode while preserving strict
  provenance checks for injected output and links, keeping APM delivery stable
  after local checker imports. Source inventory no longer traverses Git
  internals, installed Node dependencies, or test/type caches.
- Codecov uploads through GitHub OIDC from a dedicated job, CodeRabbit hardening
  for its open-source tier, and schema validation for both configurations.
- Standalone tool configuration: `ruff.toml`, `ty.toml`, `pytest.ini`,
  `.coveragerc`, `tox.ini`, `.cz.toml`, `.yamllint.yaml`,
  `.markdownlint-cli2.yaml`, `cspell.json`, `.lychee.toml`, `jscpd.json`, and a
  detect-secrets baseline, all wired into pre-commit, Task, and CI.
- Dependabot version and security updates for uv, GitHub Actions, and pre-commit
  hooks, with cooldowns, grouping, and Conventional Commit prefixes.
- Tiered test suite (`unit/`, `property/`, `integration/`) with directory-based
  markers, real-process integration tests, and 90% branch-coverage enforcement.
- Linked task-specific guides, acceptance/evidence assets and quality gates across
  the capability library, plus consumer knowledge and native-certification templates.
- Resource-depth inventory/checks integrated into coverage, explicit script
  replacement paths, and runnable portable-checker regressions.
- Native opt-in MCP examples for all 11 recorded integrations, with source,
  identity, licensing, tool-selection and removal review rather than auto-startup.
- Scoped consumer knowledge instructions and a read-only context-entry/link checker.

- Backend-only Pydantic v2 and Polars 2 skills, narrow instructions, references,
  reusable templates, and source-contract regression tests.
- Explicit session skill allowlists, integrity-hashed footprint reports, an
  on-demand context procedure/task template, and real narrow-delivery tests.
- Complete original-capability coverage, opt-in reusable procedures, native role
  delivery, configuration assets, editor wrappers, and guard/convention facades.
- Account-neutral ownership and publication gates, community governance, guarded
  draft releases, Python code scanning, and verified artifact checksums.
- Importable branch/tag rulesets, dependency review, OpenSSF Scorecard, and release
  note categories, all checked by the governance gate.
- `kit-capability-authoring` skill for agent-driven toolkit changes.
- Python docstrings use paired double-backtick inline literals, enforced by
  the shared convention checker in `task verify` and pre-commit.

### Changed

- Composed APM manifests exclude on-demand skill trees from application placement
  scans; real smoke checks all portable bundles, original resource bytes and native
  rosters in a temporary home before and after frozen installation.

- Merged duplicate instructions (five into three) and added a per-profile
  always-on context budget test.

### Fixed

- Windows workspace publication retries bounded transient sharing denials while
  preserving no-overwrite semantics and rechecking path indirection.

- Native prompt provenance binds provider projections to an authored facade
  without accepting arbitrary command files or relaxing delivery hashes.
- Session resource checks interpret Markdown links only in Markdown/index files,
  not Python subscript calls in code templates.
- OpenAPI comparison rejects non-object path maps; stream-recording checks reject
  invalid JSON separators and non-finite constants.

- `ty` silently skipped `scripts/` and `.agents/guard/` because `[tool.ty.src]`
  listed only `src` and `tests`; six latent type errors in the governance check
  are now fixed and every Python root is checked.
- Provenance ledger and composition paths must be canonical: `./x` and `a//b` were
  silently collapsed instead of rejected.
- Text files are normalized to LF as `.gitattributes` and `.editorconfig` require.
- Public issue intake is private-first: blank issues are disabled, security reports
  route to private reporting, and forms/release notes use a declared, gated label set.
- Dependency review runs only for pull requests, which provide the base/head
  dependency diff; merge-group verification remains in the main CI matrix.

## 0.1.0 - 2026-10-08

### Added

- Original APM-first capability bundles, strict policy, profile composition,
  provenance verification, native repository adapters, and quality gates.
