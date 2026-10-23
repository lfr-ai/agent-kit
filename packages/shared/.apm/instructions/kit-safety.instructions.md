---
description: Apply to implementation work across project types.
applyTo: "**"
---

- Read package ownership, generated-file markers, and nearby conventions before editing; change only the files the request needs.
- Use the repository's declared manager, lockfile, and toolchain; preserve unrelated workspace changes and leave untouched files unformatted.
- Add a dependency only when the standard library or an existing dependency cannot do the job, and state why in the change.
- Never install or run packages ad hoc (`pip install`, `npx`, `uvx`); change the manifest and lockfile, audit the lock, then install with the locked command. Pin tools, hooks, actions and images to exact versions, commits or digests.
- Keep source dependencies inward and boundary errors explicit; never swallow a failure to make a check pass.
- Keep file operations inside the workspace or an owned output directory; resolve and contain user-supplied paths.
- Do not disclose secrets, private data, or proprietary project content in code, logs, fixtures, or transcripts.
- Never read credential stores, acquire cloud identities, or call production services from an authoring session.
- Do not weaken assertions, lint rules, type checks, or policy gates to pass; fix the cause or report the gap.
- Use focused checks while iterating and the owning verification gate before handoff.
- Approval-sensitive publication, deployment, destructive actions, and global setup
  changes belong to an explicit operator workflow.
- Report exact checks run; distinguish inspection from validation, and name unavailable checks and unsupported runtime capabilities.
