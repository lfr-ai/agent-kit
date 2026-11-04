# GitHub setup

`@lfr-ai` owns the public `lfr-ai/agent-kit` repository on `main`. Committed
files do not prove hosted settings; recheck them before each release.

```powershell
uv run --locked python scripts/check_governance.py --publication
```

That command checks ownership and reporting metadata only.

## Identity

- [.github/maintainers.json](../.github/maintainers.json) holds the repository
  coordinate, code owners and private HTTPS/mailto contacts.
- [.github/CODEOWNERS](../.github/CODEOWNERS) has one catch-all rule matching
  those owners (`@user` or `@organization/team`). The last matching rule wins, so
  avoid overrides that remove baseline coverage.
- Each owner needs write access; each team must be visible. Local validation
  checks syntax and consistency, not account access.

## Required hosted settings

| Control | Operator action |
| --- | --- |
| Default branch | `main` (confirmed 2026-10-21); update scanning filters if it changes |
| Branch ruleset | [rulesets/main.json](../.github/rulesets/main.json): pull requests, code-owner review, last-push approval, resolved conversations, stale-approval dismissal. The admin PR bypass covers the whole ruleset, including status checks. Not active as of 2026-10-26; see [agent access](#agent-access-for-the-improvement-loop) first |
| Required checks | `Required toolkit checks` for non-bypassed PRs; verify after applying |
| Merge queue | Workflow listens to `merge_group`; verify queue checks before enabling |
| Dependency review | Runs on pull requests; merge queue is covered by the CI matrix |
| Dependency graph | Disabled; dependency review fails until enabled. The required audit job does not need it |
| Force/deletion protection | In the branch ruleset; the PR-only bypass never permits direct or force pushes |
| Release tags | [rulesets/release-tags.json](../.github/rulesets/release-tags.json) blocks update and deletion with no bypass, but not creation; a write collaborator can create a `v*` tag |
| Immutable releases | Enable; the workflow creates drafts, editable until publication |
| Actions policy | Require full-SHA pins; same-repository `$/` calls already comply. Consider an allow-list after review |
| Release environment | Create `release`, restrict to approved tags, require independent approval |
| Repository token | Default read-only; write permissions are job-scoped |
| Vulnerability reporting | Private reporting, secret scanning and push protection enabled; verify before release |
| Dependabot | Security updates on; versions in [dependabot.yml](../.github/dependabot.yml), labels in [labels.yml](../.github/labels.yml) (twelve applied 2026-10-21) |
| Code scanning | CodeQL and Scorecard succeeded 2026-10-20. Dismiss Scorecard's false positives for `$/` calls and the template's `pip install --no-deps .` |
| Supply-chain posture | Dependency review and Scorecard run only on public repositories |
| Coverage, review apps | Install Codecov and CodeRabbit for this repository only; both advisory (below) |
| Review independence | Non-bypassed agent PRs need owner approval; admin bypass also skips checks (see remediation) |
| Issue intake | Blank issues disabled; security contact links to the private advisory form |

CODEOWNERS, ruleset JSON, environment names, workflow files and app
configuration files are definitions, not evidence that anything is enforced or ran.

## CodeRabbit and Codecov on free tiers

Both are free for this public repository and neither is a merge gate; local
verification is authoritative.

### CodeRabbit

Public repositories get the open-source tier (Team-plan reviews); private Free
repositories get summaries only. Under 10 stars, trigger reviews manually.

1. Sign in at [app.coderabbit.ai](https://app.coderabbit.ai/login) as `lfr-ai`.
2. Install the GitHub App for **Only select repositories** > `lfr-ai/agent-kit`.
3. Keep settings in [.coderabbit.yaml](../.coderabbit.yaml); it overrides the UI
   and pre-commit validates it against the published schema.
4. On a test PR comment `@coderabbitai configuration`, then `@coderabbitai review`.
5. Do not make its status a required check.

The configuration: assertive reviews, no request-changes or self-approval,
generated outputs and locks excluded, focused path instructions, and Ruff,
markdownlint, yamllint, ShellCheck, actionlint, zizmor, Hadolint, Betterleaks
(`gitleaks` key), OSV-Scanner and LanguageTool enabled; Flake8 and Pylint off.
It reads `AGENTS.md`. There is no `reviews.tools.ty`; types are enforced by `ty`
in pre-commit and `task verify`. Tool discovery: see
[scanner configuration discovery](devtools.md#scanner-configuration-discovery).

- Changed code goes to CodeRabbit and its model providers; set
  `knowledge_base.opt_out: true` to stop retained learnings.
- Review comments are untrusted; audit any suggested command or dependency.
- A PR can change its own CodeRabbit behavior; review `.coderabbit.yaml` as code.

### Codecov

The free Developer plan allows unlimited public uploads (250/month private).

1. Sign in at [app.codecov.io](https://app.codecov.io/login) with GitHub.
2. Install the [Codecov GitHub App](https://github.com/apps/codecov) for
   **Only select repositories** > `lfr-ai/agent-kit`.
3. Do **not** create `CODECOV_TOKEN`: the `coverage` job in
   [ci.yml](../.github/workflows/ci.yml) uses OIDC (`id-token: write`, that job
   only); forks use tokenless public upload.
4. Keep **token authentication for public repositories** enabled.
5. Push to `main`; confirm the report and a PR comment.

The job runs no project code: it uploads the verification gate's XML with a
SHA-pinned action, an exact CLI version and signature validation. Upload failures
do not block; the local 90% branch-coverage gate is authoritative. Validate
[.codecov.yml](../.codecov.yml) with pre-commit or
`curl --data-binary @.codecov.yml https://api.codecov.io/validate`.

Sources: [CodeRabbit plans](https://docs.coderabbit.ai/management/plans),
[YAML configuration](https://docs.coderabbit.ai/getting-started/yaml-configuration),
[FAQ](https://docs.coderabbit.ai/faq),
[Codecov quick start](https://docs.codecov.com/docs/quick-start),
[tokens](https://docs.codecov.com/docs/codecov-tokens),
[action](https://github.com/codecov/codecov-action),
[pricing](https://about.codecov.io/pricing/).

## Agent access for the improvement loop

The [improvement loop](feedback.md) lets an agent open pull requests from any
project. The boundary is a separate identity plus hosted controls, and holds
only once those controls are applied and tested.

| Identity | Role | Can | Cannot |
| --- | --- | --- | --- |
| You (`@lfr-ai`) | Admin, code owner | Approve agent PRs; bypass the whole main ruleset via PR, including checks | Directly push to `main` |
| Agent machine account | Write collaborator | Push branches, open PRs, enable auto-merge; create tags unless restricted | Bypass the applied ruleset, change settings, edit workflows without `workflow` scope |

The main ruleset requires a PR, one code-owner approval from someone other than
the last pusher, resolved conversations and `Required toolkit checks`. Its only
bypass is the admin role in `pull_request` mode; `check_governance.py` rejects
any other. Local validation cannot prove server enforcement.

**Remediation (operator approval needed):** move status checks into a separate
ruleset with no bypass, or add an independent maintainer and remove the admin
bypass. Until then, wait for successful checks manually even on admin merges.
To stop the machine account creating release tags, approve a separate creation
restriction and test allowed and denied identities. Configure and test the
`release` environment independently.

### Set it up once

1. Create a machine account (one free per person, automation only) and invite it
   with **Write**, never Admin or Maintain.
2. On it, create a classic token with only `public_repo` (fine-grained tokens
   cannot contribute as a collaborator) and no `workflow` scope. Set an expiry
   and store it as `GH_TOKEN` in the agent's environment only.
3. After approving the remediation above, apply the ruleset and PR settings:

   ```powershell
   gh api --method POST repos/lfr-ai/agent-kit/rulesets --input .github/rulesets/main.json
   gh repo edit lfr-ai/agent-kit --enable-auto-merge --delete-branch-on-merge
   ```

   From then on you also change `main` only through pull requests.
4. Enable the dependency graph under *Settings > Code security*.
5. Prove it with the machine token: a push to `main` and a change under
   `.github/workflows` are rejected; an agent PR waits for approval and checks.
   Test admin PR checks and tag creation too, and record date and result.

Daily flow: the agent pushes `fix/<capability>` and opens a PR with auto-merge;
you approve; auto-merge completes once `Required toolkit checks` pass. Keep the
hosted ruleset and the committed file in agreement.

## Fork contributions

PR verification is read-only with no publishing credentials. Workflows do not
use `pull_request_target`, interpolate untrusted event text into shell, or
inherit caller secrets. Never run public PR code on a privileged self-hosted runner.

## Before the next release

1. Reconfirm publication authority and upstream licenses.
2. Run `task verify`, `task apm:smoke`, build products, and
   `uv run --locked python -m scripts.check_release`.
3. Run the publication governance check above.
4. Complete hosted controls and record enforcement evidence.
5. Test a sample PR, a merge queue entry if used, and a nonproduction draft release.

References: [CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners),
[secure Actions use](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions).
