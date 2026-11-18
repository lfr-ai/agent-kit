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
- Keep research downloads and temporary reports in explicit absolute
  temporary/session paths, never repository-relative output files. Retain source
  links and durable decisions in the relevant documentation; inspect root
  artifacts before handoff.
- Plan proportionately; iterate with `task check` or one focused test.
- Keep Task targets for recurring workflows; invoke individual gates through
  `task verify -- <gate>` and one-off tools directly. Rely on tool discovery and
  defaults; add an override only for an intentional, documented policy difference.
- For defects, reproduce the behavior, fix the cause, and retain regression tests.
- Explicitly report errors, unsupported runtime behavior, and unavailable checks.
- Do not weaken assertions, provenance, policy, or permission gates to pass.
- Change dependencies only through `pyproject.toml` and `uv.lock`: run
  `uv add --no-sync` (Claude denies it and VS Code requires approval, so ask a
  human to run it), then
  `task verify -- dependencies` before syncing. Never run
  ad-hoc installers or package runners such as `pip install`, `npx`, or `uvx`.
- In this repository only: read-only git is always allowed. Create a branch and
  commit only for a change the user requested in this session. Push a
  non-default branch, open a pull request, or enable auto-merge only after the
  user approves the exact command. Never push or merge to the default branch,
  force-push, rewrite pushed history, tag, release, or change repository settings.
- Write commit messages as Conventional Commits (`fix(catalog): reject unknown
  fields`); the `commit-msg` hook runs `cz check` and rejects other shapes.
- Version control in any other repository, remote publication, user-global setup
  changes, resource deployment, and production data belong to approved operator
  workflows.
- The session hook is advisory context, not authorization or a sandbox.

## Code and boundaries

- Core is stdlib-only. Dependencies flow inward.
- Application owns selection and validation; Infrastructure owns files and
  processes; Presentation owns CLI input/output; Composition wires collaborators.
- Language rules live in path-scoped instructions (Python: `kit-python`).
- Keep types concrete, errors explicit, paths contained, and changes local.
- Prefer the simplest behavior-complete design for maintainability, readability
  and low cognitive load; retrieve task-relevant context on demand.
- Package code must work when installed away from its source checkout.

## Verification and handoff

- Run `task verify` once before handoff, not after each edit; run
  `task apm:smoke` after APM-facing changes.
- Then have the read-only `kit-code-reviewer` role review the diff as a second
  pass; fix each finding or record why it stands.
- Audit existing owned outputs before any regeneration.
- Do not claim a native IDE, cloud, or model session was tested by a file test.
- Record only durable, evidenced lessons in `memories/`.
- Summarize changes, exact verification, limitations, and next actions.
- End responses with a short `tldr;`.
