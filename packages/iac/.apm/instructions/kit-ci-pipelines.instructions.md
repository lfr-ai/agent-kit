---
description: Apply to CI pipeline definitions for GitHub Actions and Azure Pipelines.
applyTo: ".github/workflows/*.yml,.github/workflows/*.yaml,.azuredevops/**/*.yml,.azuredevops/**/*.yaml,**/azure-pipelines*.yml"
---

- Run the same task-runner commands in CI that developers run locally; keep gate logic in the task runner, not duplicated in YAML.
- Pin third-party actions to a full commit SHA with a version comment, and pin pipeline templates and extensions to fixed versions.
- Declare least-privilege token permissions (`contents: read` by default) and widen them per job only when needed.
- Never interpolate untrusted event fields such as titles, branch names, or bodies into `run` scripts; pass them through environment variables and quote them.
- Do not run untrusted pull-request code with secrets or write tokens; never check out the pull-request head in `pull_request_target`.
- Use OIDC workload identity federation for cloud access instead of long-lived secrets; scope secrets to protected environments.
- Set `persist-credentials: false` on checkout unless a later step must push.
- Set job timeouts; cancel superseded pull-request runs, but never cancel an in-progress deployment.
- Install dependencies from lockfiles in frozen mode and key caches on the lockfile hash.
- Put shared logic in reusable workflows or templates with typed inputs instead of copied jobs.
- Upload only needed artifacts with short retention; never upload secrets, state files, or environment dumps.
- Gate deployment jobs behind protected environments and required reviewers; deploy jobs list the build job in `needs` and promote its digest instead of rebuilding.
- Validate workflow syntax with the available linter before pushing.
- Use the `kit-ci-review` skill for pipeline security review and the `kit-delivery-pipelines` skill for delivery design.
