# GitHub setup

## Identity first

No authenticated GitHub profile is adopted automatically.
The personal owner `@lfr-ai` was verified from the existing Ekko CODEOWNERS and
public repository owner. The reporting route follows that owner's documented
security/conduct contact.
`uv run --locked python scripts/check_governance.py --publication` checks this metadata.
The intended `lfr-ai/agent-kit` remote and its hosted settings have not been created.

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
| Default branch | Use `main`, or update the scanning workflow branch filters |
| Branch ruleset | Import [rulesets/main.json](../.github/rulesets/main.json): pull requests, code-owner review, last-push approval, resolved conversations, stale-approval dismissal, no bypass |
| Required checks | The ruleset requires `Required toolkit checks`; confirm it after the first successful hosted run |
| Merge queue | The verification workflow listens to `merge_group`; verify actual queue checks before enabling |
| Dependency review | Runs on pull requests, where GitHub provides the dependency diff's base/head commits; merge queue remains covered by the CI matrix |
| Force/deletion protection | Included in the branch ruleset; add bypass only for reviewed emergency roles |
| Release tags | Import [rulesets/release-tags.json](../.github/rulesets/release-tags.json); use an authorized release operator |
| Release environment | Create `release`, restrict it to approved tags, require independent approval, disallow self-review where available |
| Actions | Use hosted runners, restrict allowed actions, and require immutable pins |
| Repository token | Keep the default token read-only; write permissions are narrowly job-scoped |
| Vulnerability reporting | Enable private reporting and secret scanning/push protection where available |
| Dependency visibility | Enable the dependency graph, Dependabot alerts, and Dependabot security updates; version updates are configured in [dependabot.yml](../.github/dependabot.yml) and need the `dependencies` label from [labels.yml](../.github/labels.yml) |
| Code scanning | Enable Actions and verify the Python scanning workflow's first result |
| Supply-chain posture | Dependency review and OpenSSF Scorecard run only on public repositories; check their first hosted results |
| Review independence | Add a second trusted maintainer; a single owner cannot independently approve their own changes |
| Labels | Create the labels in [labels.yml](../.github/labels.yml) (UI or `gh label create`); issue forms and release-note categories use only these |
| Issue intake | Blank issues are disabled; the config links to private vulnerability reporting, which must be enabled for the link to work |

CODEOWNERS alone does not enable required approval.
Ruleset JSON files are importable definitions, not evidence they are applied.
An environment name in YAML alone does not create reviewer protection.
Workflow files alone do not prove Actions or code scanning ran.

## Fork contributions

PR verification is read-only and receives no publishing credentials.
The workflow does not use `pull_request_target`, interpolate untrusted event
text directly into shell scripts, or inherit caller secrets.
Never run public PR code on a privileged self-hosted runner.

## Before public publication

1. Verify legal/company approval and all upstream licenses.
2. Run `task verify`, `task apm:smoke`, build products, and
   `uv run --locked python -m scripts.check_release`.
3. Run `uv run --locked python scripts/check_governance.py --publication`;
   preserve the verified personal identity and contacts.
4. Complete hosted controls and record actual enforcement evidence.
5. Test a sample PR, a merge queue entry if used, and a nonproduction draft release.

Reference: [GitHub CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
and [secure Actions use](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions).
