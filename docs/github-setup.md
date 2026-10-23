# GitHub setup

## Identity first

`@lfr-ai` owns the public `lfr-ai/agent-kit` repository on `main`.
`uv run --locked python scripts/check_governance.py --publication` checks the
ownership and reporting metadata. Committed files do not prove hosted settings;
recheck rulesets, the dependency graph, Dependabot, secret scanning, push
protection, and private vulnerability reporting before each release.
The repository includes [Codecov](../.codecov.yml) and
[CodeRabbit](../.coderabbit.yaml) configuration, a Codecov OIDC upload job in
[CI](../.github/workflows/ci.yml), and the existing
[pull request template](../.github/PULL_REQUEST_TEMPLATE.md). The hosted apps must
still be installed; see [CodeRabbit and Codecov on free tiers](#coderabbit-and-codecov-on-free-tiers).

Set [.github/maintainers.json](../.github/maintainers.json) to the approved
repository coordinate, code owners, and private HTTPS/mailto contact routes.
Then set [.github/CODEOWNERS](../.github/CODEOWNERS) to one catch-all rule
matching the owners in that file. GitHub handles begin with `@`; teams use
`@organization/team`. The last matching rule wins, so this project avoids
overrides that accidentally remove baseline coverage.

Each owner must have write access and each team must be visible to the repository.
Local validation checks syntax/consistency, not account access or authorization.
An account can be real without being the approved publishing identity.

## Required hosted settings

| Control | Operator action |
| --- | --- |
| Default branch | `main` was confirmed on 2026-10-21; update the scanning filters if it changes |
| Branch ruleset | Apply [rulesets/main.json](../.github/rulesets/main.json): pull requests, code-owner review, last-push approval, resolved conversations, stale-approval dismissal, no bypass; not active as last checked |
| Required checks | The local ruleset requires `Required toolkit checks`; verify the context after applying it |
| Merge queue | The verification workflow listens to `merge_group`; verify actual queue checks before enabling |
| Dependency review | Runs on pull requests, where GitHub provides the dependency diff's base/head commits; merge queue remains covered by the CI matrix |
| Dependency graph | Still disabled; enable it before relying on the dependency-review workflow, which currently fails. The required dependency-audit job does not depend on it |
| Force/deletion protection | Included in the branch ruleset; add bypass only for reviewed emergency roles |
| Release tags | [rulesets/release-tags.json](../.github/rulesets/release-tags.json) is active; updates/deletion are blocked with no bypass actors |
| Immutable releases | Enable immutable releases so a published release's tag and assets cannot change; the workflow already creates drafts, which remain editable until publication |
| Actions policy | Require actions to be pinned to full-length commit SHAs; same-repository calls use `$/` and already satisfy that policy |
| Release environment | Create `release`, restrict it to approved tags, require independent approval, disallow self-review where available |
| Actions | Actions are currently unrestricted; workflow references are SHA-pinned and statically checked. Consider an allow-list after verifying every action |
| Repository token | Keep the default token read-only; write permissions are narrowly job-scoped |
| Vulnerability reporting | Private reporting and secret scanning/push protection are enabled; verify their current state before release |
| Dependency visibility | Dependabot security updates are enabled; dependency graph is not. Version updates are configured in [dependabot.yml](../.github/dependabot.yml) and labels in [labels.yml](../.github/labels.yml) |
| Code scanning | CodeQL and Scorecard succeeded on 2026-10-20; continue checking hosted runs |
| Supply-chain posture | Dependency review and OpenSSF Scorecard run only on public repositories; check their first hosted results |
| Code coverage | Install the Codecov GitHub App for this repository only; CI uploads with OIDC. Codecov statuses stay advisory; the local 90% branch-coverage gate is authoritative |
| Automated review | Install the CodeRabbit GitHub App for this repository only and check `@coderabbitai configuration` on a PR. Reviews are advisory; GitHub rulesets control required reviews and checks |
| Review independence | Add a second trusted maintainer; a single owner cannot independently approve their own changes |
| Labels | The twelve labels from [labels.yml](../.github/labels.yml) were applied on 2026-10-21; reconcile hosted labels after inventory changes |
| Issue intake | Blank issues are disabled; the security contact links to GitHub's private advisory form, with the maintainer contact as fallback |

CODEOWNERS alone does not enable required approval.
Ruleset JSON files are importable definitions, not evidence they are applied.
An environment name in YAML alone does not create reviewer protection.
Workflow files alone do not prove Actions or code scanning ran.
Codecov and CodeRabbit configuration files alone do not prove an integration,
coverage upload, review, or required status check is active.

## CodeRabbit and Codecov on free tiers

Both services are free for this public repository. Neither is a merge gate:
`Required toolkit checks` and code-owner review remain authoritative, so an
outage, rate limit, or incorrect review cannot silently weaken the required checks.

### CodeRabbit

Public repositories get CodeRabbit's open-source tier: Team-plan review features
without a subscription. Private repositories on the Free plan get pull-request
summaries only. Open-source review limits depend on the repository's popularity.
While the repository has fewer than 10 stars, reviews must be triggered manually
with `@coderabbitai review`.

1. Sign in at [app.coderabbit.ai](https://app.coderabbit.ai/login) with the
   `lfr-ai` GitHub account.
2. Install the CodeRabbit GitHub App and choose **Only select repositories** →
   `lfr-ai/agent-kit`. Review the requested permissions before accepting.
3. Keep repository settings in [.coderabbit.yaml](../.coderabbit.yaml); a
   committed file takes precedence over UI settings. Pre-commit validates it
   against CodeRabbit's published schema.
4. Open a test pull request and comment `@coderabbitai configuration` to see the
   resolved settings, then `@coderabbitai review` to request a review.
5. Do not add CodeRabbit's status to required checks; keep it advisory.

What the configuration does: assertive reviews; no request-changes or
self-approval; generated outputs and lockfiles are excluded; Python, workflow,
container and pinning paths receive focused instructions; Ruff, markdownlint,
yamllint, ShellCheck, actionlint, zizmor, Hadolint, Betterleaks (the `gitleaks`
key) and OSV-Scanner are enabled in CodeRabbit's sandbox. LanguageTool checks
grammar at its default level, complementing CSpell's spelling checks.
Flake8 and Pylint are off because Ruff already covers the selected rule families.
CodeRabbit automatically reads `AGENTS.md` as review guidance. Enabling a tool
does not certify it ran: hosted availability, file selection, and duplicate-CI
detection can cause tools to be skipped.

There is no `reviews.tools.ty` field in CodeRabbit's current schema. Type checking
is enforced by the pinned `ty` in pre-commit and `task verify`, using
[ty.toml](../ty.toml) for toolkit and portable Python assets. The enabled GitHub
Checks integration can provide CI results
to CodeRabbit; it does not run `ty` or replace the required checks.

See [scanner configuration discovery](devtools.md#scanner-configuration-discovery)
for which repository files each native and hosted integration reads. Most other
CodeRabbit tools are enabled by default and selected by file type; this explicit
list is not an exhaustive catalog or a reason to enable unrelated language tools.

Be aware that:

- Changed code and context are sent to CodeRabbit and its model providers.
  CodeRabbit states it does not train on customer code. Learnings are limited to
  this repository; set `knowledge_base.opt_out: true` to disable features that
  retain code-related data.
- Review comments are untrusted suggestions. Never apply a suggested command or
  dependency without the normal audit and review.
- The configuration on the pull request branch is used for that review, so a PR
  can change its own CodeRabbit behavior. Review `.coderabbit.yaml` changes as code.

### Codecov

Codecov's free Developer plan covers one user with unlimited public-repository
uploads (private repositories are limited to 250 uploads per month).

1. Sign in at [app.codecov.io](https://app.codecov.io/login) with GitHub.
2. Install the [Codecov GitHub App](https://github.com/apps/codecov) for
   **Only select repositories** → `lfr-ai/agent-kit`; it is required for PR
   comments and statuses.
3. Do **not** create a `CODECOV_TOKEN` secret. The `coverage` job in
   [ci.yml](../.github/workflows/ci.yml) authenticates with GitHub OIDC
   (`id-token: write`, granted to that job only). Fork pull requests cannot mint
   OIDC tokens, so they use Codecov's tokenless upload for public repositories.
4. Keep **token authentication for public repositories** enabled in the
   organization's Codecov settings; OIDC already satisfies it for protected
   branches, and it prevents unauthenticated uploads to `main`.
5. Push to `main`, then confirm the report under the repository in Codecov and a
   coverage comment on the next pull request.

The upload job runs no project code: it downloads the coverage XML produced by
the verification gate and uploads it with the action pinned to a commit, the
Codecov CLI pinned to an exact version, and the action's signature validation on.
Upload failures are non-blocking by design. Validate [.codecov.yml](../.codecov.yml)
changes with pre-commit, or with Codecov's validator:
`curl --data-binary @.codecov.yml https://api.codecov.io/validate`.

Sources: [CodeRabbit plans](https://docs.coderabbit.ai/management/plans),
[CodeRabbit YAML configuration](https://docs.coderabbit.ai/getting-started/yaml-configuration),
[CodeRabbit FAQ](https://docs.coderabbit.ai/faq),
[Codecov quick start](https://docs.codecov.com/docs/quick-start),
[Codecov tokens](https://docs.codecov.com/docs/codecov-tokens),
[Codecov action](https://github.com/codecov/codecov-action), and
[Codecov pricing](https://about.codecov.io/pricing/).

## Fork contributions

PR verification is read-only and receives no publishing credentials.
The workflow does not use `pull_request_target`, interpolate untrusted event
text directly into shell scripts, or inherit caller secrets.
Never run public PR code on a privileged self-hosted runner.

## Before the next release

1. Reconfirm publication authority and all upstream licenses.
2. Run `task verify`, `task apm:smoke`, build products, and
   `uv run --locked python -m scripts.check_release`.
3. Run `uv run --locked python scripts/check_governance.py --publication`;
   preserve the verified personal identity and contacts.
4. Complete hosted controls and record actual enforcement evidence.
5. Test a sample PR, a merge queue entry if used, and a nonproduction draft release.

Reference: [GitHub CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
and [secure Actions use](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions).
