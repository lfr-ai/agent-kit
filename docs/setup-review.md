# Existing setup review and capability disposition

Use the [coverage manifest](../.agents/agentic-setup/coverage.json) for each
original capability's replacement or exclusion, [sources](sources.md) for dated
inventory/research, and the [adoption walkthrough](setup-completeness.md) for steps.

## Resource-depth refresh, 2026-10-19

Identity mapping is not resource depth. The
[resource gate](../scripts/check_resources.py) checks reachable references/assets,
guidance and script paths; [sources](sources.md#resource-depth-refresh-2026-10-19)
records the refresh. Native certification and consumer facts still need evidence.

## Why the first toolkit was incomplete

The architecture pilot lacked the inventory/disposition and resource-depth
contracts required by the [current acceptance plan](setup-completeness.md#1-acceptance-plan).
It was not a complete replacement.

## Current ownership

| Original surface | New owner | Difference |
| --- | --- | --- |
| agentic-setup selection | [Root catalog](../catalog.json) and coverage manifest | One selection schema |
| reusable skills | Package `.apm/skills/` | Original procedures; consolidated overlapping workflows |
| scoped instructions | Package `.apm/instructions/` | Generated native rules with selected scope |
| agents/subagents | Selected skill role assets | Shared bodies, separately rendered native permissions |
| static guard | Installed validation plus `.agents/guard/` facade | No duplicate giant guard implementation |
| editor commands | Thin Task wrappers and reusable editor assets | No application-specific commands or personal shortcuts |
| MCP | [Native manifests and package `apm.yml`](mcp-adoption.md) | Reviewed delivery, optional startup; no committed credentials or project identities |
| hooks | Advisory session health plus a delivered Git-guard hook (`shared`) | No claimed universal shell sandbox |
| project facts/knowledge | Consumer remains owner | Toolkit has its own facts; consumer context is not copied |

Compare an available original checkout with the recorded baseline:
`uv run --locked python -m scripts.check_coverage --source-root <original-checkout>`.
This compares capability identities, not secrets.

## Consolidation, not hidden deletion

- OpenSpec maps to one lifecycle workflow; verify commands against the installed
  tool, not a copied upstream command set or byte-identical template promise.
- Graph procedures map to one impact/context workflow; local consumer indexing
  is optional for small edits. Ponytail maps to original simplification/debt
  guidance, not redistributed plugin bodies.
- Language/domain/browser/AI/operations procedures retain separate triggers.
- Pydantic v2 and Polars 2 procedures are backend-only and opt-in; validation and
  analytics types remain outside domain Core.
- `kit-testing` merges into `kit-test-author`; `kit-tdd` into the `kit-test-first`
  skill plus `kit-test-author`; `kit-fullstack`, `kit-frontend` and
  `kit-ai-engineer` into `kit-orchestrator`. Only selected-stack roles ship.
  [Native permissions](editor.md#native-discovery-and-menu) keep workers hidden;
  verifiers get an offline shell but no edit or delegation tools.

## Deliberate exclusions

- Copier/scaffolding, company pipeline IDs and medical publication stay outside
  portable scope; application facts, migrations, deployment identities and license
  policy remain consumer-owned.
- App DI/port/migration guards stay in the app until a tested portable validator
  supports its schema. Terraform/Azure what-if reviewers accept only documented
  input shapes and never authorize apply.
- Descriptive skill invocation replaces command facades, not operator-controlled
  release/deployment approval.

## Guard changes and limits

[scripts/verify.py](../scripts/verify.py) owns separate source, budget, resource,
coverage, role, provenance, policy and toolchain gates.
The [verification contract](verification.md) distinguishes static checks from
live IDE/cloud behavior. No check authorizes apply or makes arbitrary shell safe.
Post-action hooks cannot undo installation; consumer locked-license gates enforce
adoption/publication policy.

## Provenance and public redistribution

The [provenance record](sources.md) owns authorship and upstream research.
Function mapping does not permit stripping graph/OpenSpec/Ponytail attribution
or licenses; proprietary prompts and unverified upstream bodies are not portable
source.

Existing applications and user-global configuration remain unchanged.
