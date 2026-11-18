# Consumer templates

A project generator such as [Copier](https://copier.readthedocs.io/) chooses a
profile reference and renders it into the consumer's `apm.yml`. It should not
copy Agent Kit's skills, instructions, hooks or agents: APM owns package resolution,
integrity, installation, compilation and updates.

## One profile reference

The **consumer repository** declares the profile it needs. For a Python backend:

```yaml
name: my-service
version: "0.1.0"
targets: [copilot, claude]
dependencies:
  apm:
    - lfr-ai/agent-kit/profiles/backend#<reviewed-tag>
  mcp: []
```

`backend` is a compact meta-package whose pinned dependencies are the catalog's
`shared` plus `backend` source packages and the two native role packages.
Each native dependency uses APM 0.35.0 object-form `targets` selection and the
same reviewed tag. Do not list those transitive packages in the
consumer manifest: APM resolves them through the profile reference. The
resulting `apm.lock.yaml` records the resolved source revisions and hashes.
Commit both the manifest and lock.

| Consumer need | Profile reference |
| --- | --- |
| Shared conventions, no stack | `lfr-ai/agent-kit/profiles/shared#<reviewed-tag>` |
| Python backend | `lfr-ai/agent-kit/profiles/backend#<reviewed-tag>` |
| React frontend | `lfr-ai/agent-kit/profiles/frontend#<reviewed-tag>` |
| Full-stack | `lfr-ai/agent-kit/profiles/fullstack#<reviewed-tag>` |
| Infrastructure | `lfr-ai/agent-kit/profiles/iac#<reviewed-tag>` |
| Terraform or OpenTofu | `lfr-ai/agent-kit/profiles/terraform#<reviewed-tag>` |
| Bicep | `lfr-ai/agent-kit/profiles/bicep#<reviewed-tag>` |
| AI application | `lfr-ai/agent-kit/profiles/ai#<reviewed-tag>` |
| Durable workflows | `lfr-ai/agent-kit/profiles/temporal#<reviewed-tag>` |
| Identity | `lfr-ai/agent-kit/profiles/identity#<reviewed-tag>` |
| Specification and audit workflows | `lfr-ai/agent-kit/profiles/workflows#<reviewed-tag>` |
| Remote access | `lfr-ai/agent-kit/profiles/remote-access#<reviewed-tag>` |

The Copier starter uses generated combination profiles under
`lfr-ai/agent-kit/profiles/starters/<slug>#<reviewed-tag>`. Their catalog IDs
retain `starter-`; only the generated directory slug omits that redundant
prefix.

Use the profile that already includes the capabilities you need. If you add
multiple profiles, first check for overlapping files and verify their combined
installation in a disposable consumer; do not assume overlapping packages are
merged safely.

## Consumer policy

The consumer owns and reviews its APM policy. A minimal starting point is the
[policy template](../.apm/skills/kit-apm-adopt/assets/apm-policy.yml.template).
For Agent Kit profiles, allow the profile and source-package paths, including
`lfr-ai/agent-kit/profiles/native/copilot` and
`lfr-ai/agent-kit/profiles/native/claude`, and only the
MCP names needed by the selected profile. Each profile manifest declares the
selected MCP configuration directly, so the template keeps
`mcp.trust_transitive: false`.

For a source-free consumer, declare `includes: []` and retain
`require_explicit_includes: true` in policy. This accepts a deliberate opt-out
but rejects missing or automatic includes. Do not also put `includes` in
`required_fields`: that separate rule requires a nonempty value.

APM 0.35.0 does not automatically apply every local policy file during
installation. Run `apm policy status --policy-source ./apm-policy.yml --check
--json` and `apm audit --ci --policy ./apm-policy.yml` in CI. Where available,
enforce the same rules through organization-managed APM policy; a local file
alone is not an install-time security boundary.

## Install, compile and update

From the consumer repository:

```powershell
apm install --target copilot,claude --no-trust-bin
apm compile --target copilot
apm compile --target claude
apm audit --ci --policy ./apm-policy.yml
```

Review the installed files and lock before accepting them. CI should use
`apm install --frozen --target copilot,claude --no-trust-bin` followed by
`apm audit --ci --policy ./apm-policy.yml`. Frozen installation fails instead
of refreshing a missing or stale lock.

For one host, select only `copilot` or `claude` in the consumer's `targets` and
the install/compile commands. Every selected host receives `kit-orchestrator`,
`kit-debug` and all 16 canonical workers, with provider-specific tools,
visibility and any authored model preferences unchanged. The other host's
native agents are not installed.

To update, change the profile tag to a reviewed release, run `apm install`,
inspect the lock diff and installed files, then commit the reviewed update. To
roll back, restore the previous `apm.yml` and `apm.lock.yaml`. Never edit the
lock by hand.

## Source repository versus consumer repository

This repository is the **source repository**. Maintainers edit
`packages/*/.apm/`, package `apm.yml` manifests and `catalog.json`;
`profiles/<name>/apm.yml` is generated from that canonical source. It contains
only the profile's pinned package dependencies and selected MCP configuration,
not copied capabilities. The shared `profiles/native/{copilot,claude}` packages
contain generated `.apm/agents/` primitives, rendered from canonical role assets
by the same renderer as the repository projections. APM does not read `catalog.json`: it resolves the
generated profile manifest. The profile generator and validation tasks are
maintainer tools, not consumer commands.

The **consumer repository** owns its app, application checks, policy, project
facts, private knowledge and secrets. It adds one profile reference to its own
`apm.yml`, installs with APM, and commits its own lockfile. It does not need to
clone Agent Kit or install an Agent Kit Python package.

## Optional project templates

A project scaffold may ask for a profile name and reviewed release tag, then
render the single `dependencies.apm` entry. It should leave runtime-specific
settings, host permissions, MCP credentials and application quality gates to
the consumer. Do not copy generated `.github/`, `.claude/` or skill directories
into templates; that creates stale, independently-owned copies.

## Evidence and limits

The native profile smoke is designed to install through released APM into relocated consumers
using local replacement rules, not a published tag or a pre-populated discovery
tree. It checks filenames and exact metadata/body bytes for Copilot-only,
Claude-only and both, followed by audit and frozen replay.
See [compatibility](compatibility.md) for recorded results, timeout limits and
the recovered legacy deployment-ledger issue. Local replacement tests do not
certify native IDE/model sessions, publication of a release tag or downloading
that release in a fresh consumer.
