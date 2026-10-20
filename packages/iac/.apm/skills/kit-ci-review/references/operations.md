# Workflow operations: structure, concurrency, and cost bounds

## Structure

- Separate validation (lint, test, build) from publication (push, release,
  deploy). Publishing jobs depend on validation through `needs:` and run only
  on protected refs or tags.
- Extract repeated job logic into reusable workflows (`on: workflow_call`) with
  typed `inputs:` and explicitly listed `secrets:`. Avoid `secrets: inherit`
  for workflows outside your control; it forwards every secret.
- A called workflow can only reduce the caller's token permissions. Declare
  `permissions:` in both caller job and called workflow so either file shows
  the effective grant.
- Composite actions bundle steps but cannot declare permissions or secrets;
  they inherit the job's environment. Prefer reusable workflows when a job
  boundary or a separate permission set is needed.

## Concurrency

- Add a `concurrency:` group keyed by workflow and ref for pull request
  validation with `cancel-in-progress: true` so superseded pushes stop.
- For deployments, use a group per environment with `cancel-in-progress: false`
  so a running deployment is never interrupted halfway.

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

## Bounds

- Set `timeout-minutes:` on every job; the platform default is six hours.
- Keep matrices bounded and use `fail-fast` deliberately.
- Restrict path filters (`paths:`) carefully: a required check that never runs
  blocks merges unless a companion job reports success.
- Use `workflow_dispatch` inputs with `type: choice` rather than free text when
  inputs drive branching.

## Required checks and branch protection

- Required status checks must be stable job names. Renaming a job silently
  removes the requirement until settings are updated.
- Avoid `if:` conditions that skip a required job and report success on the
  paths you meant to protect.
- Protect release tags with rulesets so only release workflows can create them.

## Shell defaults

- Bash steps on hosted Linux runners use `bash -e {0}` by default. Set
  `defaults: run: shell: bash` to get `--noprofile --norc -eo pipefail`, so
  failures inside pipelines also fail the step.
- Quote every variable expansion and avoid `eval`.

## Review checklist

- [ ] Validation and publication are separate jobs with `needs:` ordering.
- [ ] Reusable workflows receive explicit inputs and named secrets.
- [ ] Every job has `timeout-minutes`; pull request runs cancel superseded runs.
- [ ] Deploy concurrency never cancels an in-flight deployment.
- [ ] Required checks cannot be skipped into a green state.

Start from the [hardened CI template](../assets/templates/ci.yml.template) and
the [reusable build template](../assets/templates/reusable-build.yml.template).

## Sources

- <https://docs.github.com/en/actions/sharing-automations/reusing-workflows>
- <https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs>
- <https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions>
- <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets>
