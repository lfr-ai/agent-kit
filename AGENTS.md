# Agent Kit operating policy

Read [PROJECT.md](PROJECT.md) for commands and [llms.txt](llms.txt) for context.

## Scope

- Author reusable capabilities under `.apm/` and `packages/*/.apm/`.
- Keep runtime metadata and permissions in their native adapters.
- Generated capabilities are not independently authored copies.
- Keep project facts, credentials, personal memory, and proprietary content out
  of portable bundles.
- Review the owning source and test behavior before changing a policy.

## Working method

- Inspect relevant code and prior patterns before editing.
- Plan proportionately; use focused checks while iterating.
- Keep Task targets for recurring workflows; invoke individual gates through
  `task verify -- <gate>` and one-off tools directly. Rely on tool discovery and
  defaults; add an override only for an intentional, documented policy difference.
- For defects, reproduce the behavior, fix the cause, and retain regression tests.
- Explicitly report errors, unsupported runtime behavior, and unavailable checks.
- Do not weaken assertions, provenance, policy, or permission gates to pass.
- Version-control operations, remote publication, user-global setup changes,
  resource deployment, and production data belong to approved operator workflows.
- The session hook is advisory context, not authorization or a sandbox.

## Code and boundaries

- Core is stdlib-only. Dependencies flow inward.
- Application owns selection and validation; Infrastructure owns files and
  processes; Presentation owns CLI input/output; Composition wires collaborators.
- No production `Any`, casts, or quoted forward-reference annotations.
- Immutable dataclasses use `frozen=True`, `kw_only=True`, and `slots=True`.
- Use stdlib `import logging`; do not duplicate logging at multiple boundaries.
- Keep types concrete, errors explicit, paths contained, and changes local.
- Package code must work when installed away from its source checkout.
- Parameterized initializers document their arguments.

## Verification and handoff

- Run `task verify` before handoff; run `task apm:smoke` after APM-facing changes.
- Audit existing owned outputs before any regeneration.
- Do not claim a native IDE, cloud, or model session was tested by a file test.
- Record only durable, evidenced lessons in `memories/`.
- Summarize changes, exact verification, limitations, and next actions.
- End responses with a short `tldr;`.
