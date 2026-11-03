# Agent Kit

APM-first, opt-in capabilities with strict source checks and reproducible provenance.

## Start

Install the [prerequisites](CONTRIBUTING.md#pull-requests), then run from the checkout:

```powershell
task bootstrap
task verify
uv run agent-kit compose backend --root . --output build/backend
uv run agent-kit provenance --root build/backend
task apm:smoke
```

The pinned APM CLI is a dev dependency. Composition requires a **new** output
path; existing destinations fail. It never overwrites consumer or personal settings.

## Select capabilities

| Profile | Selection |
| --- | --- |
| shared | Hexagonal architecture, conventions, context, testing, editor, and agent workflows |
| backend | Shared plus Python domain, API, persistence, configuration, Pydantic v2, Polars 2, and packaging |
| frontend | Shared plus accessible React, state, routing, forms, and browser testing |
| fullstack | Deduplicated backend/frontend union |
| iac | Shared plus infrastructure, containers, CI, edge, API gateways, delivery, and observability |
| terraform | IaC plus Terraform/OpenTofu plan review on any cloud |
| bicep | IaC plus Bicep/ARM what-if review (Azure-native) |
| remote-access | IaC plus SSH, `sshd_config` hardening, and bastions |
| workflows | Optional specification, graph, duplication, and simplification workflows |
| ai | Optional retrieval, model client, workflow, queue, and streaming procedures |
| temporal | Backend plus deterministic workflows, Activities, retries, replay tests, and Temporal documentation MCP |
| identity | Shared plus Entra/OIDC, API token verification, scopes, roles, and frontend authorization |
| toolkit | This repository's APM governance and shared kernel |

Add a profile as `--feature` to extend another. Choose the IaC tool, not the
cloud: provider-specific detail lives in templates that load only when used.

```powershell
uv run agent-kit compose fullstack --feature terraform --runtime copilot --runtime claude --output build/fullstack
```

Add durable execution or identity only where needed:

```powershell
uv run agent-kit compose backend --feature temporal --feature identity --output build/service
```

Generators and CI can declare the same choice in a versioned file instead of
flags; see [consumer templates](docs/consumer-templates.md):

```powershell
uv run agent-kit compose --selection agent-kit.json --output build/agent-kit
```

For a narrow backend session, explicitly select its procedures:

```powershell
uv run agent-kit compose backend --skill kit-python-service --runtime copilot --output build/session-backend
```

Repeat `--skill` as needed. Sessions keep general instructions, policy and the
Git guard, but omit native roles, prompt facades and MCP. Same-named skill
instructions follow the allowlist. Unknown IDs or missing linked skills fail
before output: add a linked skill explicitly rather than auto-expanding.
Inspect `.apm/selection.json` for IDs and character counts, not billed tokens.
Use a separate reviewed workspace for isolation; a subfolder cannot suppress
parent/global skills, plugins or tools.

- [Catalog](catalog.json) owns selection. Skills and resources live in APM bundles.
- [Setup walkthrough](docs/setup-completeness.md), [migration/rollback](docs/migration.md),
  and [VS Code setup](docs/editor.md) cover adoption.
- [Policy](docs/policy.md), [MCP adoption](docs/mcp-adoption.md),
  [verification](docs/verification.md) and [compatibility](docs/compatibility.md)
  define enforcement and tested/runtime limits.
- [Setup review](docs/setup-review.md), [capability review](docs/capability-review.md)
  and [sources](docs/sources.md) cover disposition, topic coverage and provenance.
- [Improve the kit](docs/feedback.md) covers approved contributions from any project.
- [Hexagonal Architecture](.agents/knowledge-base/architecture.md) covers source boundaries.
- [Agentic setup](.agents/agentic-setup/README.md) indexes the authoritative catalog and guard.
- [Support](SUPPORT.md), [contributing](CONTRIBUTING.md), and [governance](GOVERNANCE.md)
  explain participation and ownership.
- [GitHub setup](docs/github-setup.md) and [releasing](docs/releasing.md) distinguish
  local readiness from hosted protections and publication.

## Distribution

This pre-release toolkit is not a globally installed service or marketplace.
[PROJECT.md](PROJECT.md#identity) owns version/repository identity.
Operators configure hosted protections and publish reviewed releases;
existing projects are untouched.

`task capabilities:build -- --profile fullstack --feature iac` produces a licensed
APM source ZIP. Extract it before using APM; it is not a plugin or a locked
dependency bundle. Python distributions contain the CLI; capability source stays
in the toolkit repository or the selected source archive.

MIT applies to the original contents. Dependency and referenced-source licenses
remain their own. Company publication approval is still required where applicable.

`task verify -- governance` checks local ownership/community/workflow contracts.
`uv run --locked python scripts/check_governance.py --publication` adds personal
owner/private-contact checks, not account inference or hosted certification.

`task verify -- coverage` checks replacements;
`uv run --locked python -m scripts.check_resources --json` checks linked resources.
Identity coverage alone is insufficient. `task verify` includes canonical
configuration checks; see the [verification contract](docs/verification.md).
APM delivers the Git guard in every profile and MCP by selected package.
[Policy](docs/policy.md#delivered-hooks-and-mcp-servers) owns delivery and safety limits;
other integration examples require consumer adoption, not automatic startup.
