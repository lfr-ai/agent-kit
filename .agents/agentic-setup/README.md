# Capability selection and delivery

This directory indexes the toolkit's canonical selection and coverage contracts.
It is not another authored copy of skills or runtime configuration.

- [Catalog](../../catalog.json): Profiles, bundles, inheritance, budgets.
- [Profiles](profiles.md): Each profile's bundles, inheritance, roles, consumer,
  composition and verification.
- [Technology coverage](technology-coverage.md): Technologies mapped to owning
  instructions, skills, roles and profiles, with regeneration commands.
- [Design rationale](design-rationale.md): Why APM-first, selected delivery,
  budgets, provenance, advisory hook, opt-in MCP and rendered native roles.
- [Repository selection](self.json): Profile, features and runtimes rendered for
  this repository's own roles; [ownership ledger](native-lock.json) records their hashes.
- [Coverage](coverage.json): Every original capability and its disposition.
- [Asset index](assets.json): Actual resource locations, not copied asset bodies.
- [Migration analysis](../../docs/setup-review.md): Gaps, replacements, and exclusions.
- [Complete setup walkthrough](../../docs/setup-completeness.md): Acceptance plan,
  resource depth, consumer knowledge/gates and native/MCP adoption.
- [Hexagonal Architecture](../knowledge-base/architecture.md): Layer and ownership boundaries.
- [Guard](../guard/verify_agent_config.py): Relocation-safe facade for existing checks.

Portable procedures and their resources live under package-owned `.apm/skills/`.
Provider agents are rendered from selected role assets; their bodies share one
source while tools and delegation metadata follow the native host contract.

Run `task verify -- coverage` to detect missing/disappearing replacements and
`task verify` for the full gate. Features remain opt-in; available is not active.
Run `uv run --locked python -m scripts.check_resources --json` for the actual per-skill resource census.
The coverage gate also rejects checklist-only or unreachable resource delivery;
this minimum structure does not itself establish semantic completeness.
