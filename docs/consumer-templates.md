# Consumer templates

A project generator such as [Copier](https://copier.readthedocs.io/) should
choose **which packages** a project uses. It should not copy their files.
APM still owns resolution, the lockfile, integrity, policy and drift checks;
copied skills would bypass all of them and go stale silently.

## Why select by tool, not by cloud

Every installed skill adds its name and description to every session, so a
project should receive only what it uses
([Agent Skills](https://agentskills.io/specification.md),
[context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).
Skill bodies, references and templates load only when used. Provider-specific
detail therefore costs nothing until it is read, and it lives in templates.

What differs between projects is the IaC **tool**. Each tool has its own
validation procedure, so each tool is an opt-in feature:

| Project uses | Packages |
| --- | --- |
| No infrastructure | `shared` plus the application profile |
| Terraform or OpenTofu, any cloud | `iac`, `terraform` |
| Bicep or ARM on Azure | `iac`, `bicep` |
| CloudFormation, SAM, CDK, Pulumi or Crossplane | `iac` (the `kit-cloud-iac` instruction loads for those files) |
| SSH, `sshd_config` or bastion automation | add `remote-access` |

Packages do not depend on each other; name each one. A cloud-specific package
would duplicate the shared review procedure across three clouds without
reducing what loads.

## What the optional workflows package does

The `workflows` package adds procedures, not an orchestration service. It does
not start agents, create Git commits, run a scheduler or deploy resources.
Install `shared` plus `workflows` when a change needs a specification, an impact
analysis or a structured codebase audit; skip it for ordinary small fixes.

For example, adding CSV export:

1. `/kit-spec-explore add-csv-export`: describe the problem and alternatives;
   do not implement.
2. `/kit-spec-propose add-csv-export`: write a small proposal for acceptance.
3. Before `/kit-spec-apply`, complete requirements and the task plan. A
   requirement can be as small as:

   ```text
   Given two allowed records
   When the user exports CSV
   Then a header and two rows are returned
   ```

4. `/kit-spec-apply add-csv-export`: implement only the agreed tasks and tests.
5. `/kit-spec-verify add-csv-export`: record real results for the scenarios.
6. `/kit-spec-archive add-csv-export`: retain the accepted specification and
   archive the change's evidence.

The [lifecycle contract](../packages/workflows/.apm/skills/kit-spec-workflow/references/lifecycle.md)
defines the complete stages and folder layout. The shorthand above does not
skip Specify or Plan. These prompts are procedures, not guaranteed command-line
programs; the host must discover the installed prompt.

Other workflows cover impact graphs, duplication, simplification, audits and
modernization. Use one relevant procedure rather than loading all of them.
For recurring mistakes in those procedures, use the existing
[capability evaluation loop](../packages/shared/.apm/skills/kit-feedback-loop/references/skill-evaluations.md)
to compare baseline and candidate behavior in a local, synthetic project.

## Template answers

Ask for the tool and derive the cloud only where the tool implies it. Copier
supports `choices`, `when` and Jinja defaults in `copier.yml`:

```yaml
cloud_provider:
  type: str
  help: Primary cloud
  choices: [none, azure, aws, gcp]
  default: none

iac_tool:
  type: str
  help: Infrastructure as code tool
  choices:
    None: none
    Terraform or OpenTofu: terraform
    Bicep: bicep
    CloudFormation, CDK or Pulumi: other
  default: "{{ 'bicep' if cloud_provider == 'azure' else 'terraform' if cloud_provider != 'none' else 'none' }}"
  validator: "{% if iac_tool == 'bicep' and cloud_provider != 'azure' %}Bicep deploys only to Azure{% endif %}"

remote_access:
  type: bool
  help: Does the project automate SSH or bastion access?
  default: false
  when: "{{ iac_tool != 'none' }}"

agent_kit_ref:
  type: str
  help: Reviewed Agent Kit release tag
  default: v0.1.0
```

## Path A: project APM install (recommended)

Render the `dependencies` section of `apm.yml.jinja` with only the selected
virtual packages, pinned to a reviewed tag (`owner/repo/path#ref`):

```yaml
dependencies:
  apm:
    - lfr-ai/agent-kit/packages/shared#{{ agent_kit_ref }}
    - lfr-ai/agent-kit/packages/backend#{{ agent_kit_ref }}
{%- if iac_tool != 'none' %}
    - lfr-ai/agent-kit/packages/iac#{{ agent_kit_ref }}
{%- endif %}
{%- if iac_tool in ['terraform', 'bicep'] %}
    - lfr-ai/agent-kit/packages/{{ iac_tool }}#{{ agent_kit_ref }}
{%- endif %}
{%- if remote_access %}
    - lfr-ai/agent-kit/packages/remote-access#{{ agent_kit_ref }}
{%- endif %}
  mcp: []
```

After generation, run `apm install` once and commit `apm.yml` and
`apm.lock.yaml`. CI runs `apm install --frozen`, which refuses a lockfile that
is missing or out of sync with the manifest, then `apm audit`.

Prefer `_message_after_copy` over `_tasks` for the install step. Copier runs
`_tasks` only with `--trust`, and installation belongs in a reviewed change.

## Path B: composed package

Generators that need native agent roles, or one reviewed artifact, render a
selection file and compose it:

```json
{
  "schema_version": 1,
  "profile": "backend",
  "features": ["terraform"],
  "runtimes": ["copilot", "claude"]
}
```

```powershell
uv run agent-kit compose --selection agent-kit.json --output build/agent-kit
uv run agent-kit provenance --root build/agent-kit
```

| Field | Required | Value |
| --- | --- | --- |
| `schema_version` | yes | `1` |
| `profile` | yes | A catalog profile |
| `features` | no | Profiles merged into the selection; `terraform` includes `iac` |
| `runtimes` | no | `copilot`, `claude`; defaults to both |
| `skills` | no | Session allowlist; omits native roles |

The file is closed: unknown fields, repeated names, duplicate JSON keys,
symlinks and files over 64 KiB are rejected before anything is written. The
composed selection must still fit the profile description budget. `--selection`
cannot be combined with a positional profile or with `--feature`, `--runtime`
or `--skill`. Then follow [adoption](migration.md) for installation.

## Updating

`copier update` re-renders the manifest or selection file from the stored
answers; changing `iac_tool` swaps the package. Bump `agent_kit_ref` in the
answers to adopt a new release, then review the regenerated lockfile.

## Migrating a template that copies capability files

A template that copies `.github/copilot-instructions.md`, `.claude/` or skill
directories owns stale duplicates. Replace those files with the rendered
`apm.yml`, keep project-specific facts in the project's own `AGENTS.md`, and
remove the copies in the same reviewed change.
