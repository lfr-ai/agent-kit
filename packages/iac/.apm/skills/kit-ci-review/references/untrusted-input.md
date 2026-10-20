# Untrusted input and privileged triggers

Workflow expressions (`${{ ... }}`) are expanded by the runner before the shell
starts. Any attacker-controlled string that reaches a `run:` script therefore
becomes code, regardless of shell quoting around it. This is the most common
critical finding in workflow reviews.

## Attacker-controlled contexts

Treat these as untrusted whenever the triggering actor can be outside the
maintainer group:

- `github.event.pull_request.title`, `.body`, `.head.ref`, `.head.label`
- `github.event.issue.title`, `.body`; `github.event.comment.body`
- `github.event.review.body`, `github.event.review_comment.body`
- `github.event.pages.*.page_name`, `github.event.commits.*.message`,
  `github.event.head_commit.message`, `.author.email`, `.author.name`
- `github.head_ref`
- Outputs of steps that processed any of the above, and artifacts or caches
  produced by an untrusted run.

## Safe pattern

Pass values through an intermediate environment variable and reference the
variable with shell quoting. The runner sets the variable as data; the shell
never parses it as script.

```yaml
- name: Echo title safely
  env:
    TITLE: ${{ github.event.pull_request.title }}
  run: printf '%s\n' "$TITLE"
```

Inside `actions/github-script`, read `context.payload` or `process.env`
instead of interpolating expressions into the JavaScript source.

## Privileged triggers

`pull_request_target` and `workflow_run` run in the context of the base
repository with access to its secrets and a write-capable token, even when the
change came from a fork.

- Never check out and execute the pull request head (`ref:
  ${{ github.event.pull_request.head.sha }}`) inside a `pull_request_target`
  job. Building, installing dependencies, or running tests from that ref hands
  the attacker the base repository's token and secrets.
- If a `pull_request_target` workflow is needed (for labeling or commenting),
  keep it free of checkout of untrusted code and limit `permissions:` to the
  exact scopes it uses.
- For "run tests, then comment" flows, split into an unprivileged
  `pull_request` workflow that uploads results as an artifact and a
  `workflow_run` workflow that downloads them as data. Validate artifact
  content before use and never execute it.
- `issue_comment` triggers also run with base privileges; gate commands on
  `github.event.comment.author_association` and treat the comment text as data.

## Self-hosted runners

- Do not attach self-hosted runners to public repositories. A fork pull request
  can run arbitrary code on the host.
- Use ephemeral, just-in-time runners and isolate runner groups per trust level.

## Review checklist

- [ ] No `${{` expression from an untrusted context appears in `run:`.
- [ ] `pull_request_target` and `workflow_run` jobs never execute fork code.
- [ ] Artifacts from untrusted runs are parsed as data, not executed.
- [ ] Comment-triggered commands check the author association.

The [workflow checker](../assets/check_workflow_permissions.py) reports every
`${{` inside a `run:` value. Allow-list only expression prefixes you have
proven safe (for example `--allow-expression runner.`).

## Sources

- <https://docs.github.com/en/actions/reference/security/secure-use>
- <https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#pull_request_target>
- <https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#workflow_run>
- <https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners>
