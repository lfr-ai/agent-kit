# Agent Kit

[![CI](https://github.com/lfr-ai/agent-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/lfr-ai/agent-kit/actions/workflows/ci.yml)
[![CodeQL](https://github.com/lfr-ai/agent-kit/actions/workflows/codeql.yml/badge.svg)](https://github.com/lfr-ai/agent-kit/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/lfr-ai/agent-kit/badge)](https://securityscorecards.dev/viewer/?uri=github.com/lfr-ai/agent-kit)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Reusable, opt-in guidance for AI coding agents—distributed as pinned
[APM](https://github.com/microsoft/apm) packages for GitHub Copilot and Claude
Code.

**Consumers install a named profile with APM. They do not need an Agent Kit
Python package or `agent-kit` command.** The `apm` command below is Microsoft's
APM installer.

## Why use it?

- Start with one stack-specific profile instead of a large, always-on prompt.
- Keep reusable guidance in one reviewed source, with pinned installs and
  explicit update and rollback paths.
- Ship procedures alongside templates and runnable checks—not just advice.

**Status:** pre-release (0.1.0). Source validation and disposable APM smoke
checks are automated; these do not certify every agent host, model or published
profile. See [tested contracts and limits](docs/compatibility.md).

No release is published yet (checked 2026-11-04). To try the current source, use
the [contributor workflow](#contributing); the consumer walkthrough below
requires a reviewed release and is not runnable with its placeholder.

## Install a profile in your project

These steps are for a **consumer repository**—the application or service where
you want to use the guidance. You need Git and the
[APM CLI](https://github.com/microsoft/apm#installation); the maintainer-tested
version is 0.33.0. You do not need this repository's Python/Bun toolchain.
Choose a reviewed release containing the profile you need, then add one
profile reference to your project's root `apm.yml`:

```yaml
name: my-service
version: "0.1.0"
targets: [copilot, claude]
dependencies:
  apm:
    - lfr-ai/agent-kit/profiles/backend#<reviewed-tag>
  mcp: []
```

`backend` already includes `shared`; you do not add `packages/shared` separately.
Replace `<reviewed-tag>` with a published release tag that contains the profile manifests. The
placeholder is not an installable version; if no suitable release exists,
profile adoption is not ready.

Before auditing, save and review the
[consumer policy template](.apm/skills/kit-apm-adopt/assets/apm-policy.yml.template)
as `apm-policy.yml` in your project. Allow the chosen profile and source-package
paths and only the MCP servers you intend to use. Then install, compile and
audit:

```powershell
apm install --target copilot,claude --no-trust-bin
apm compile --target copilot
apm compile --target claude
apm audit --ci --policy ./apm-policy.yml
```

The profile declares its selected MCP
configuration directly, so transitive MCP trust can stay disabled. The lockfile
records the resolved source revisions and integrity data; review and commit
`apm.lock.yaml`. In CI, use
`apm install --frozen` and `apm audit` so the reviewed lock and installed files
are checked rather than refreshed silently.

> **APM policy note:** APM 0.33.0 does not automatically apply every
> project-local policy file during installation. A successful policy-status
> check is not an install-time enforcement boundary; wire policy and audit
> checks into CI. See [policy and trust boundaries](docs/policy.md).

## Choose a profile

| Profile | Includes | Good starting point for |
| --- | --- | --- |
| `shared` | Shared guidance | Any repository, without a specific stack |
| `backend` | `shared` + `backend` | Python services, APIs, persistence and packaging |
| `frontend` | `shared` + `frontend` | React and TypeScript clients |
| `fullstack` | `shared` + `backend` + `frontend` + `coordination` | Applications maintained across client and server |
| `iac` | `shared` + `iac` | Infrastructure, containers and delivery |
| `terraform` | `shared` + `iac` + `terraform` | Terraform or OpenTofu |
| `bicep` | `shared` + `iac` + `bicep` | Bicep and ARM on Azure |
| `remote-access` | `shared` + `iac` + `remote-access` | SSH, bastion and remote access |
| `workflows` | `shared` + `workflows` | Specification, audit and simplification workflows |
| `ai` | `shared` + `backend` + `ai` | Retrieval, model clients and AI evaluation |
| `temporal` | `shared` + `backend` + `temporal` | Durable workflows and replay-safe tests |
| `identity` | `shared` + `identity` | Entra ID, OIDC, scopes and roles |

Use one profile for the common case. Add another package only when you
intentionally need an independent capability set; profile selection does not
isolate you from guidance or tools already supplied by your agent host.

## Two repositories, two responsibilities

### Agent Kit source repository

This repository is where maintainers edit reusable source under
`packages/*/.apm/` and define profile membership in [`catalog.json`](catalog.json).
The catalog records inheritance, budgets and validation rules. It is not read by
APM at install time.

The generated `profiles/` directories contain compact APM meta-package
manifests. Each references the pinned source packages selected by the catalog;
no skills, instructions or assets are copied. That is why a consumer can
reference `backend` once while the generated manifest pins its `shared` and
`backend` source-package closure. The generated manifests are checked against
their canonical sources and should not be edited by hand. The APM smoke checks
source-package delivery; it does not certify resolution of a released profile's
dependency closure (see [compatibility](docs/compatibility.md)).

Maintainers use repository tasks—not a consumer-facing Agent Kit CLI:

```powershell
task profiles:build
task verify -- source
task apm:smoke
```

### Consumer repository

The consumer owns its root `apm.yml`, `apm.lock.yaml`, policy, application
checks, project facts, private knowledge and secrets. APM installs the selected
profile into that repository's agent-tool locations. To update, change the
reviewed profile reference, run `apm install`, review the lock and resulting
files, then commit the change. To roll back, restore the previous reference and
lock.

## What profiles deliver—and what they do not

Profiles package the selected APM instructions, skills, prompts, hooks and
declared MCP configuration. APM then handles installation, compilation,
integrity and auditing. A profile is a convenience package, not a sandbox or a
replacement for host permissions, application tests or security review.

Native agent-role files are currently generated for this repository's own
Copilot and Claude setup; they are **not** included in consumer profile
packages. See [compatibility](docs/compatibility.md) for what has and has not
been verified.

## Why APM and the catalog?

- **APM is the consumer install path.** It resolves a pinned package reference,
  records the lock, compiles for the selected hosts and audits installed files.
- **The catalog is the source-repository authoring index.** It describes which
  reusable bundles make up each profile and lets maintainers validate those
  selections before publishing.
- **Generated profile meta-packages connect the two.** APM consumes one small
  package manifest and resolves its pinned source-package dependencies; it does
  not interpret Agent Kit's catalog or profile inheritance. The manifest also
  declares the selected MCP configuration directly, so consumers can keep
  transitive MCP trust disabled.

## Documentation

| Topic | Guide |
| --- | --- |
| Step-by-step consumer adoption | [Setup walkthrough](docs/setup-completeness.md) |
| Consumer templates and package references | [Consumer templates](docs/consumer-templates.md) |
| Package and MCP trust | [APM policy](docs/policy.md), [MCP adoption](docs/mcp-adoption.md) |
| Compatibility limits | [Compatibility](docs/compatibility.md) |
| Capability evaluation cases and observation limits | [Evaluation instructions](tests/evals/README.md) |
| Profile source and generated packages | [Profile reference](.agents/agentic-setup/profiles.md) |
| Contributing and governance | [Contributing](CONTRIBUTING.md), [governance](GOVERNANCE.md) |
| Maintainer commands | [PROJECT.md](PROJECT.md) |

## Contributing

For work on **this repository**, install the prerequisites in
[Contributing](CONTRIBUTING.md), then run:

```powershell
task bootstrap
task verify
task apm:smoke
```

Bootstrap installs locked development tools and Git hooks; on Windows it also
registers the checkout path in your user environment. It is not a consumer
installation step. See [developer tooling](docs/devtools.md) for focused checks.

Read [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md) and
[SUPPORT.md](SUPPORT.md). Report vulnerabilities through [SECURITY.md](SECURITY.md).
Found incorrect reusable guidance? Follow the
[improvement loop](docs/feedback.md); include a small synthetic reproduction,
not private project code.

## License

[MIT](LICENSE). Dependencies and referenced sources keep their own licenses.
