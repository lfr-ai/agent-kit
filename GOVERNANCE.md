# Governance

## Roles and authority

- Maintainers review changes, triage reports, approve policy changes, and publish releases.
- Contributors submit focused proposals and tests through pull requests.
- Hosting administrators configure permissions, required checks, and release approval.
- Ownership is explicit in [.github/maintainers.json](.github/maintainers.json).
  No personal or organization profile is inferred from authentication.

## Decisions

Use a pull request for implementation or a design issue for cross-cutting changes.
Document compatibility and rollback for policy, profile, permission, or runtime changes.
Portable capability content keeps one authoring owner; generated delivery is reviewed.
Maintainers decide unresolved technical questions and record durable decisions.

## Reviews

- Require passing verification and an independent review before merging.
- Require code-owner review for owned changes; protect CODEOWNERS itself.
- Dismiss stale approvals after new changes and resolve review conversations.
- Avoid approving and releasing one's own change without a second reviewer.
- A sole-maintainer project cannot provide independent review until a second
  trusted maintainer is added; document the temporary limitation.

## Publication status

The personal owner is `@lfr-ai`; the intended repository is `lfr-ai/agent-kit`.
Ownership and reporting contacts follow that owner's existing Ekko records,
not the authenticated work profile. Publication metadata validation is enforced.
The remote repository has not been created; hosted branch protection or private
vulnerability reporting is not claimed enabled.
See [GitHub setup](docs/github-setup.md).
