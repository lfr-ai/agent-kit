---
name: kit-git-hooks
description: Use when adding or reviewing pre-commit, commit-msg and pre-push hooks.
license: MIT
---

# Run local Git hooks as fast feedback, with CI as the boundary

Git hooks run on a developer's machine, before a commit or push exists. They
catch cheap mistakes early and can always be skipped, so they are a
convenience layer. The required checks live in CI and branch protection.

## Procedure

1. Inventory what exists before adding anything: the hook runner
   (`.pre-commit-config.yaml`, `lefthook.yml`, a `.husky` or custom
   `core.hooksPath` directory), the declared gate (task runner or script) and
   the CI workflow. Keep the runner the repository already uses; never run two
   runners for the same hook.
2. Choose the runner with the [runner and stage guide](references/runner-and-stages.md).
   Default to pre-commit for repositories that mix languages and want
   versioned, shareable hook repositories; use lefthook when the checks are the
   project's own commands, parallel execution matters and a single binary is
   preferred. Record the decision and the reason in the
   [review record](assets/git-hooks-review.md.template).
3. Assign every check to a stage and a time budget. Formatters and linters on
   staged files run at `pre-commit`; message rules at `commit-msg`;
   whole-project type checks, unit tests and the dependency lock check at
   `pre-push`; slow, networked or full-history scans at `manual` and in CI.
   Start from the [pre-commit template](assets/pre-commit-config.yaml.template).
4. Keep hooks check-only for code. A hook that rewrites files may fix only
   whitespace and line endings; code formatters run as an explicit local action
   so a commit never silently changes reviewed code.
5. Validate the commit message with Conventional Commits and commitizen
   ([commit messages and secrets](references/commit-msg-and-secrets.md),
   [contributor guidance](assets/commit-msg-guidance.md.template)). Under squash
   merges, CI validates the pull-request title instead of every commit.
6. Add secret scanning with one primary scanner and one baseline. This
   repository family uses detect-secrets with an audited baseline; gitleaks
   suits history scans. The same scanner runs in CI over all files
   ([scanner choice](references/commit-msg-and-secrets.md#choosing-the-scanner)).
7. Pin every hook revision to a full commit SHA with a version comment, update
   it only with `pre-commit autoupdate --freeze` in a reviewed change, and run
   project-local tools through the lockfile (`uv run --locked`, `bun run --bun`)
   so hooks, CI and the editor share one version.
8. Install hooks in the bootstrap step, not on the first commit. Declare
   `default_install_hook_types` so one command installs `pre-commit`,
   `commit-msg` and `pre-push`. A set `core.hooksPath` blocks the pre-commit
   installer; resolve it deliberately.
9. Apply the bypass policy ([bypass and agent hooks](references/bypass-and-agent-hooks.md)):
   people may skip a hook only with a stated reason, and agents never run
   `--no-verify`, `-n` or `SKIP=` on a commit or push. A failing hook is fixed,
   not routed around.
10. Make CI re-run everything the hooks do, on all files, with the same pinned
    tools, and make that job required in branch protection (the
    `kit-verify-change` skill's pre-commit and CI parity guidance covers the
    single-definition approach).
11. Measure the budget: time each stage on a typical change. Over budget means
    move the hook to a later stage or narrow its `files`, never disable it.
12. Separate the two hook layers in documentation. Agent `preToolUse` hooks
    filter an agent's tool calls and Git hooks filter commits; neither replaces
    the other, and neither is a sandbox.
13. Prove it: run the stage commands on a scratch change with one deliberate
    failure per hook family (format, secret, message, test) and record the
    outputs in the review record.

## Acceptance gates

- One runner owns the hooks; its configuration and any `core.hooksPath` are
  recorded in the review record.
- Every hook repository revision is a full commit SHA, and project-local hooks
  call locked tools; no `latest`, branch name or package runner download.
- The `pre-commit` stage stays within its recorded time budget; heavier gates
  sit at `pre-push`, `manual` or CI.
- A `commit-msg` check rejects a malformed message, and a seeded fake secret is
  rejected by the scanner (use an obviously fake value from the baseline's
  allowed fixtures, never a real credential).
- CI re-runs the same checks on the whole tree and is a required status check.
- Neither the hook configuration nor agent instructions allow `--no-verify` as a
  routine step.
- The review states what was executed and what was only inspected; a file check
  is not evidence that hooks ran in a developer environment.

## Failure modes

- Hooks are slow, so contributors skip them and then skip them always.
- Hooks rewrite code during the commit, so the committed tree differs from the
  reviewed one.
- A hook runs a different tool version from CI, so local and CI results diverge.
- A secret baseline is regenerated to make a hook pass, which accepts the leak.
- Hook revisions float on tags, so a moved tag changes behavior
  without a diff.
- An agent skips a failing hook with `--no-verify` and reports the work as done.
- The only enforcement is the local hook, so a push from a machine without hooks
  bypasses everything.

Start from the [runner and stage guide](references/runner-and-stages.md).
