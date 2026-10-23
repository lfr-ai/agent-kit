# Existing setup review and capability disposition

Reviewed 2026-10-09 against the committed capability inventory and repository
checks.
The original baseline contained 74 skills, 31 instructions, 24 agent roles,
24 prompt facades, 22 skill scripts, 11 MCP integrations, five asset bundles,
and three hooks. The initial read-only inventory missed three script identities;
they are now explicitly tracked.

## Resource-depth refresh, 2026-10-19

Identity mapping alone did not establish comparable capability depth. The
library now has a structural contract requiring each skill's reachable reference
and asset, task-specific acceptance/failure guidance, a real resource census,
and regression checks for losing those resources. Consumer knowledge, context
entry checking and actual native-certification worksheets are delivered as
resources rather than fabricated application facts.

All 11 MCP integrations have both native example shapes and explicit adoption,
tool-selection, source/license, identity and removal review. The repository
workspace configures only three reviewed remote servers; portable APM defaults
remain inactive. See the [systematic walkthrough](setup-completeness.md) for
acceptance and operator work.

## Why the first toolkit was incomplete

It intentionally had eight short skills, one repository reviewer, a compact
catalog, and only an advisory session hook. That was a minimal architecture pilot,
not a full extraction. It lacked a complete inventory/disposition contract.
Calling that a replacement for the original capabilities was inaccurate.

## Current ownership

| Original surface | New owner | Difference |
| --- | --- | --- |
| agentic-setup selection | Root catalog plus this directory's coverage index | One selection schema, not another profiles mirror |
| reusable skills | Package `.apm/skills/` | Original procedures; consolidated overlapping workflows |
| scoped instructions | Package `.apm/instructions/` | Generated native rules with selected scope |
| agents/subagents | Selected skill role assets | Shared bodies, separately rendered native permissions |
| static guard | Installed validation plus `.agents/guard/` facade | No duplicate giant guard implementation |
| editor commands | Thin Task wrappers and reusable editor assets | No application-specific commands or personal shortcuts |
| MCP | Three reviewed remote services in native root manifests; inactive templates for all 11 integrations | No committed credentials, project identities, or default APM activation |
| hooks | Advisory session health and native authorization contract | No claimed universal shell sandbox |
| project facts/knowledge | Consumer remains owner | Toolkit has its own facts; consumer context is not copied |

The [coverage manifest](../.agents/agentic-setup/coverage.json) gives every original
skill, instruction, and agent an actual replacement or explicit exclusion.
`uv run --locked python -m scripts.check_coverage --source-root <original-checkout>` compares the live
source identities to the recorded baseline without reading secrets.

## Consolidation, not hidden deletion

- Twelve OpenSpec procedures map to one lifecycle workflow. Native commands must
  be checked against the installed tool; there is no copied/generated upstream
  command set or promise of byte-identical templates.
- Six graph procedures map to one impact/context workflow; indexing stays local
  to the consumer and is not required for every small edit.
- Five Ponytail modes map to original simplification/debt guidance, not a
  redistributed third-party plugin or brand.
- Language/domain/browser/AI/operations procedures retain separate task triggers.
- Pydantic v2 and Polars 2 procedures are backend-only and opt-in; validation and
  analytics types remain outside domain Core.
- The full native role roster is retained, but only the selected stack's roles
  are delivered. Read-only workers cannot gain edit, shell, or delegation tools.

## Deliberate exclusions

- Copier/scaffolding integration remains outside scope as requested.
- Company pipeline IDs and medical prompt publication remain consumer-specific.
- Full application blueprints, migrations, deployment identities, and dependency
  license rules are not fabricated generic production defaults.
- Existing application DI/port/migration checks stay in the owning app until a
  separately tested portable validator supports its schema.
- Read-only plan-output reviewers support explicitly documented Terraform and
  Azure what-if shapes; they neither replace application guards nor authorize apply.
- Command facades are superseded by descriptive skill invocation, not arbitrary
  shell commands that could bypass operator-controlled release/deployment.

## Guard changes and limits

The original giant guard checked many structural parity conventions. The new
checks validate source metadata, profiles, budget, resources, coverage, native
roles, task wiring, provenance, policy and APM-owned output separately.
The reusable Python checker preserves concrete AST invariants while Ruff, ty,
and import contracts enforce the established toolchain checks.

These checks are not equivalent to all original app-specific guards or proof of
live IDE/cloud behavior. They do not start MCP, run infrastructure applies, or
make arbitrary shell code safe. Post-action license hooks cannot undo an install;
consumer-owned locked license gates are the authoritative enforcement.

## Provenance and public redistribution

Procedures were written originally. No proprietary application prompts or
unverified upstream skill/resource bodies were copied.
The original graph/OpenSpec/Ponytail families have separate upstream histories;
function mapping is not permission to strip their attribution or licenses.
Provider documentation was checked for native frontmatter and activation.

Existing applications and user-global configuration remain unchanged.
