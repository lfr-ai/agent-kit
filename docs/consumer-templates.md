# Consumer templates

A project generator such as [Copier](https://copier.readthedocs.io/) chooses a
profile reference and renders it into the consumer's `apm.yml`. It should not
copy Agent Kit's skills, instructions or hooks: APM owns package resolution,
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
`shared` plus `backend` source packages. Do not list both source packages in the
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

Use the profile that already includes the capabilities you need. If you add
multiple profiles, first check for overlapping files and verify their combined
installation in a disposable consumer; do not assume overlapping packages are
merged safely.

## Consumer policy

The consumer owns and reviews its APM policy. A minimal starting point is the
[policy template](../.apm/skills/kit-apm-adopt/assets/apm-policy.yml.template).
For Agent Kit profiles, allow the profile and source-package paths, and only the
MCP names needed by the selected profile. Each profile manifest declares the
selected MCP configuration directly, so the template keeps
`mcp.trust_transitive: false`.

APM 0.33.0 does not automatically apply every local policy file during
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

To update, change the profile tag to a reviewed release, run `apm install`,
inspect the lock diff and installed files, then commit the reviewed update. To
roll back, restore the previous `apm.yml` and `apm.lock.yaml`. Never edit the
lock by hand.

## Source repository versus consumer repository

This repository is the **source repository**. Maintainers edit
`packages/*/.apm/`, package `apm.yml` manifests and `catalog.json`;
`profiles/<name>/apm.yml` is generated from that canonical source. It contains
only the profile's pinned package dependencies and selected MCP configuration,
not copied capabilities. APM does not read `catalog.json`: it resolves the
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

## Current limitation

Consumer profile packages do not currently include native agent-role files.
Those are rendered for Agent Kit's own repository from role metadata in skill
assets. See [compatibility](compatibility.md) before depending on role discovery
in a consumer host.
