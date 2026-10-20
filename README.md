# Agent Kit

APM-first, opt-in capabilities with strict source checks and reproducible provenance.

## Start

```powershell
uv sync --locked
task verify
uv run agent-kit compose backend --root . --output build/backend
uv run agent-kit provenance --root build/backend
task apm:smoke
```

The pinned APM CLI is a development dependency. Composition writes a **new**
package and never overwrites a consumer repository or personal settings.

## Select capabilities

| Profile | Selection |
| --- | --- |
| shared | Hexagonal architecture, conventions, context, testing, editor, and agent workflows |
| backend | Shared plus Python domain, API, persistence, configuration, Pydantic v2, Polars 2, and packaging |
| frontend | Shared plus accessible React, state, routing, forms, and browser testing |
| fullstack | Deduplicated backend/frontend union |
| iac | Shared plus infrastructure, containers, CI, and observability |
| workflows | Optional specification, graph, duplication, and simplification workflows |
| ai | Optional retrieval, model client, workflow, queue, and streaming procedures |
| toolkit | This repository's APM governance and shared kernel |

```powershell
uv run agent-kit compose fullstack --feature iac --runtime copilot --runtime claude --output build/fullstack
```

For a narrow backend session, explicitly select its procedures:

```powershell
uv run agent-kit compose backend --skill kit-python-service --runtime copilot --output build/session-backend
```

Repeat `--skill` as needed. Session packages retain general project instructions
and policy, include a skill-specific instruction only when its same-named skill
is selected, and omit the custom-agent roster. Unknown IDs and missing linked
skills fail before writing output. Inspect `.apm/selection.json` for selected
skill/instruction IDs and authored character counts; if a retained project
instruction links to another skill, add that skill explicitly. Counts are not
billed token estimates.
Use a separate reviewed workspace for native session isolation: a subfolder
cannot override parent/global skills, plugins or tool exposure.

- [Catalog](catalog.json) owns selection. Skills and resources live in APM bundles.
- [Policy](docs/policy.md) explains explicit enforcement and its limits.
- [Migration](docs/migration.md) covers adoption and rollback.
- [Compatibility](docs/compatibility.md) separates tested CLI contracts from live sessions.
- [Hexagonal Architecture](.agents/knowledge-base/architecture.md) covers source boundaries.
- [Sources](docs/sources.md) records research and licensing provenance.
- [Verification](docs/verification.md) defines the local/CI evidence contract.
- [VS Code setup](docs/editor.md) covers golden-reference alignment, interpreter,
  formatting, tasks, debugging and native-agent boundaries.
- [Setup review](docs/setup-review.md) explains every original capability's disposition.
- [Complete setup walkthrough](docs/setup-completeness.md) gives acceptance criteria,
  resource-depth checks, knowledge/guard wiring and all 11 optional MCP integrations.
- [Agentic setup](.agents/agentic-setup/README.md) indexes the authoritative catalog and guard.
- [Support](SUPPORT.md), [contributing](CONTRIBUTING.md), and [governance](GOVERNANCE.md)
  explain participation and ownership.
- [GitHub setup](docs/github-setup.md) and [releasing](docs/releasing.md) distinguish
  local readiness from hosted protections and publication.

## Distribution

This is an initial 0.1.0 toolkit, not a globally installed service or a published
marketplace. The intended personal host is `lfr-ai/agent-kit`, with owner `@lfr-ai`.
Operators create the remote, configure protected reviews, and publish reviewed
releases. Existing projects are untouched.

`task capabilities:build -- --profile fullstack --feature iac` produces a licensed
APM source ZIP. Extract it before using APM; it is not a plugin or a locked
dependency bundle. Python distributions contain the CLI; capability source stays
in the toolkit repository or the selected source archive.

MIT applies to the original contents. Dependency and referenced-source licenses
remain their own. Company publication approval is still required where applicable.

`task verify -- governance` validates local ownership/community/workflow contracts.
`uv run --locked python scripts/check_governance.py --publication` validates the configured personal owner and private
contacts; it does not infer an account from authentication or prove hosted protections.

`task verify -- coverage` rejects disappearing skill/instruction/agent replacements.
`uv run --locked python -m scripts.check_resources --json` inventories actual linked references, assets and
portable scripts for every canonical skill; identity coverage alone is insufficient.
`task verify` includes the canonical configuration checks without another guard engine.
MCP integrations remain explicitly opt-in resources; none start automatically.
