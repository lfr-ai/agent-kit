# CI review guide: gates, failure modes, and evidence

This guide is the entry point for the detailed references. Use it to decide
which reference applies and what evidence closes the review.

## Reference map

| Concern | Reference |
| --- | --- |
| Token scopes, OIDC, environments | [Permissions and tokens](permissions-and-tokens.md) |
| Script injection, `pull_request_target`, `workflow_run` | [Untrusted input](untrusted-input.md) |
| SHA pinning, Dependabot, caches, attestations | [Supply chain](supply-chain.md) |
| Reusable workflows, concurrency, timeouts, required checks | [Operations](operations.md) |

## Quality gates

- Every workflow declares top-level `permissions:`; write scopes appear only on
  the jobs that use them; no `write-all`.
- Every external action and reusable workflow is pinned to a full commit SHA
  with a version comment, and Dependabot updates the pins.
- No untrusted context is interpolated into `run:`; values flow through `env:`.
- `pull_request_target`, `workflow_run`, and comment triggers never execute
  code from the triggering pull request.
- Publishing and deployment jobs are bound to protected environments and use
  OIDC rather than stored cloud credentials.
- Every job has a timeout; pull request runs cancel superseded runs; deploys do
  not cancel each other.

## Failure modes

- A mutable tag moves to malicious code and every pinned-by-tag consumer runs it.
- A pull request title containing shell metacharacters executes in a job that
  holds a write token.
- A `pull_request_target` workflow checks out the fork head and runs its build
  scripts with repository secrets.
- A cache written by an untrusted branch is restored into a release build.
- A renamed job silently drops a required status check.

## Negative cases the checker must flag

- `uses: actions/checkout@v4`, `uses: owner/action@main`, `uses: owner/action`.
- `uses: docker://alpine:3` without `@sha256:`.
- A workflow file with `on:` but no top-level `permissions:`.
- `permissions: write-all` at any level.
- `run: echo "${{ github.event.issue.title }}"` inline or inside a block scalar.

## Recovery

1. Pin every flagged action to the SHA of the reviewed release and add the
   version comment; enable Dependabot for `github-actions`.
2. Move untrusted values into `env:` and quote the shell variable.
3. Split privileged triggers into an unprivileged build and a data-only
   follow-up workflow.
4. If a secret may have been exposed, rotate it first, then review audit logs
   and workflow run history for the exposure window.

## Prerequisites

- The changed workflow files and any reusable workflows or composite actions
  they call.
- Repository or organization settings for default token permissions, allowed
  actions, environments, and required checks (ask the owner when not visible).

## Assets

- [Workflow checker](../assets/check_workflow_permissions.py): stdlib scanner,
  `python check_workflow_permissions.py .github/workflows`, prints
  `path:line: message`, exits 1 on findings, 2 on unreadable input, and offers
  `--trusted-owner`, `--allow-expression`, `--no-require-permissions`, and
  `--self-test`.
- [Hardened CI template](../assets/templates/ci.yml.template),
  [reusable build template](../assets/templates/reusable-build.yml.template),
  and [Dependabot template](../assets/templates/dependabot.yml.template).
  Their `PIN_FULL_COMMIT_SHA` placeholders deliberately fail the checker until
  replaced with reviewed SHAs.
- [Permission and approval record](../assets/templates/ci-permissions-template.md).

## Limits

The checker is line-based. It does not evaluate YAML anchors, expressions in
`if:` conditions, or the effective permissions inherited by called workflows,
and it cannot know whether a pinned SHA is trustworthy. A `run:` key with no
inline value whose first child line is `key: value` is treated as a
`defaults.run` settings mapping, not a script. Exit 0 is a mechanical
precondition, not an approval.

## Sources

- <https://docs.github.com/en/actions/reference/security/secure-use>
- <https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions>
