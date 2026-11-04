# Design rationale

This document explains the current APM-first delivery model and the boundaries
it protects. Its source of truth is the implementation and linked policy, not
historical CLI behavior.

## Summary

| Choice | Protects | Main cost |
| --- | --- | --- |
| APM for consumer delivery | Consumers use the established package installer | Depends on a pinned external CLI |
| Catalog-generated meta-packages | One pinned dependency resolves a complete profile without copying capabilities | Nested package policy and MCP declarations need review |
| Catalog budgets | Bounded discovery metadata and profile size | Detail belongs in on-demand resources |
| Source and generated-output hashes | Detectable drift and unowned files | Hashes are not signatures or authorization |
| Advisory session hook | Honest context-entry health signal | Provides no tool filtering or access control |
| Opt-in MCP | No implicit server startup or credentials | Consumers review integrations explicitly |
| Rendered native roles | Shared role bodies with host-correct metadata | Native role outputs are repository-owned, not in consumer profiles |

## Authoring source and consumer delivery

Portable capabilities are authored in `packages/*/.apm/`; repository-specific
governance is authored in the root `.apm/`. The
[catalog](../../catalog.json) is the source for bundle membership, profile
inheritance and budgets. It is not an APM manifest and APM does not read it.

The maintainer generator emits a compact APM manifest for each portable profile
under `profiles/`. It pins the source-package closure selected by the catalog
and declares its MCP configuration directly; capability files are not
duplicated. A consumer can pin one reference such as
`lfr-ai/agent-kit/profiles/backend#v0.1.0`. In the **consumer repository**, APM
resolves, installs and compiles that dependency closure; the consumer owns its
manifest, lockfile, source allowlist and runtime-specific policy. The distinction
and complete installation steps are in the
[consumer walkthrough](../../docs/setup-completeness.md).

This is why both the catalog and profile directories exist: the catalog keeps
selection canonical and reviewable in the source repository; generated
meta-package manifests are the format APM actually installs in consumer
repositories.

Rejected alternatives:

- **Requiring consumers to list every bundle.** This duplicates catalog
  inheritance in each consumer manifest and makes a profile a manual convention
  rather than one package reference.
- **Asking APM to install a catalog profile name.** APM resolves package
  references, not this repository's catalog.
- **A second consumer-facing installer or composer.** It duplicates APM's
  installation, compilation and locking responsibilities.

## Generated-output ownership

`profiles/` is generated and must not be edited by hand. The profile lock records
the expected output hashes; the build/check workflow detects missing, extra or
changed files before updating delivery. Repository-owned Copilot and Claude
role projections have a separate source selection and native ownership ledger.
These checks detect drift; they do not prove that a capability behaves well in
a live model session.

The generated consumer profiles resolve APM source packages, not native Copilot
or Claude role files. Role definitions remain authored as skill assets and are
rendered for this repository's own native setup. Do not interpret the role
assets or local native projections as consumer-installed roles.

## Bounded discovery and budgets

The catalog declares budgets for policy lines, skill body lines, skill
descriptions, and aggregate profile descriptions. The source-validation gate
checks those limits alongside package metadata and resource validity.

Why: descriptions are loaded during discovery, so their aggregate size affects
always-on context. Procedures stay concise; detailed steps live in linked
`references/` and `assets/` opened when needed.

Trade-off: authors must split content without losing reachability. The resource
gate checks linked references and resources; passing structural checks alone
does not establish semantic completeness.

## Policy and MCP

The root [APM policy](../../apm-policy.yml) governs Agent Kit's own APM
operations. It blocks unapproved dependencies, MCP servers, lifecycle scripts
and executables, and requires explicit package content. A consumer's policy is
separate: consumers must review and configure their own policy for the selected
profile. A successful source check or install does not mean a consumer policy
was applied or that a native host enforced it.

MCP remains opt-in. Tool configuration can disclose requests to remote services
and may inherit a user's account permissions. Consumers should keep credentials
in host-managed authentication, narrow tool access, and explicitly approve each
integration. Profile smoke tests do not start MCP servers.

## Advisory session hook

The repository's native session hook runs the bounded
[session context script](../../scripts/session_context.py) and emits advisory
context about the workspace and expected entry files. It is not a consumer
installation mechanism, policy validator, or permission boundary. Native
registration and interpreter selection are checked separately; file tests do
not certify a live IDE session.

## Native role rendering

Role definitions are authored once as JSON assets inside skills
(`.apm/skills/<skill>/assets/agents.json`). The repository renderer produces
host-specific Copilot and Claude role metadata and records ownership in its
native ledger. Host tool names, delegation and visibility flags differ, so
these projections are not interchangeable.

These are repository-owned outputs. The consumer profile manifests do not
include native role projections, and the APM source-package smoke does not claim
role discovery in a consuming IDE.

## Verification boundaries

Use the [maintainer verification guide](../../docs/verification.md) for exact
commands. Source validation checks authoring inputs; profile validation checks
generated manifests and hashes; APM smoke exercises source-package installation,
compilation and frozen replay in disposable consumer projects. The smoke does
not yet certify dependency resolution through a published profile tag. Each
check proves a different boundary.

APM lockfiles record package resolution and integrity for an installation.
They are not source-provenance signatures, authorization grants or proof of
runtime behavior. Likewise, successful generation and static checks do not
certify a live IDE, model, cloud or MCP session.
