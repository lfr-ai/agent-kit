# Improve the kit from any project

Reusable agent guidance lives only here. When a skill, instruction, prompt or
template misbehaves in a project, fix it once in this repository; every project
receives the change on its next update.

## Adopt a profile in a consumer project

```powershell
apm install
apm compile --target copilot
apm compile --target claude
apm audit --ci --policy ./apm-policy.yml
```

First add one reviewed profile reference to the **consumer repository's** root
`apm.yml`, for example
`lfr-ai/agent-kit/profiles/backend#<reviewed-tag>`. Replace the placeholder
with a published release that contains the profile manifests. The `backend`
profile already includes `shared`. APM owns the consumer's manifest, lockfile,
generated files and updates; no Agent Kit CLI or globally installed Agent Kit
package is required. See the [consumer walkthrough](setup-completeness.md) and
[policy limits](policy.md).

To update, change the profile tag to a reviewed release, run `apm install`,
review the lock and installed-file diff, then commit both. For routine work in
the **Agent Kit source repository**, maintainers instead edit canonical source,
regenerate `profiles/`, and run the repository verification tasks.

## Change a capability

Run `/kit-improve <what went wrong>` in the session where you saw the problem.
The [kit-improve skill](../packages/shared/.apm/skills/kit-improve/SKILL.md):

1. Classifies the change; a fact about one project stays in that project.
2. Traces the installed file with `apm find <path> --source`.
3. Verifies the kit checkout (origin, clean tree) and edits only `.apm/` or
   `packages/*/.apm/` source.
4. Reproduces the problem with a synthetic example, retains a regression and
   runs `task verify`. Changed agent behavior also needs observed evaluation,
   not a Markdown or packaging pass.
5. Commits on a branch when asked, then waits for your approval before pushing,
   opening the pull request and enabling auto-merge.
6. You approve on GitHub; auto-merge completes when required checks pass.

After merge and release, update the consumer's pinned profile and lock, then
confirm the installed file changed. Deferred ideas go in a *Capability change*
issue.

## Close the evidence loop

1. Define the expected outcome and failure case before changing guidance. Use
   synthetic inputs; do not copy private traces into a public issue or bundle.
2. Keep the failing baseline and a regression. For agent behavior, include
   positive, negative and boundary cases; freeze the candidate before testing
   held-out tasks. Use the existing [evaluation contract](../tests/evals/README.md).
3. Compare baseline and candidate under the same host, model, tools and context,
   in fresh sessions. Inspect actual outputs and workspace changes. Repeat
   consequential cases and report every attempt, not just the best run.
4. Run deterministic gates after the final edit. Report checks, costs/latency
   when measured, regressions and missing evidence separately. The observation
   checker validates record completeness; only observed runs in the named host
   provide behavioral evidence.
5. After approved release and consumer update, rerun the original case against
   the installed revision. Roll back on a regression rather than relaxing the
   acceptance check. No publishing or permission widening is automatic.

The [source record](sources.md#feedback-and-hygiene-review-2026-11-04) separates
official guidance from empirical research. These practices support a feedback
loop; they do not establish that this kit improves every model or task.

| Class | Lane | Version effect |
| --- | --- | --- |
| Project fact | The project's own instructions | None |
| Trivial (typo, link, wording) | Pull request | Patch |
| Behavior (wrong steps, broken template) | Pull request with failing prompt and expected result | Patch or minor |
| Contract (rename, remove, widen tools or policy) | Issue, then a `breaking` pull request | Minor while 0.x |
| Security | Private advisory, immediate patch | Patch |

## Approval boundaries

Git rules are in [AGENTS.md](../AGENTS.md). Host enforcement is a speed bump:

| Host | Enforcement | Limit |
| --- | --- | --- |
| Claude Code | `ask` and `deny` rules in `.claude/settings.json` | Prefix rules miss spellings such as `git -C . push` |
| VS Code | `false` rules in `chat.tools.terminal.autoApprove` | Require approval but cannot block; `/yolo` bypasses them |
| GitHub Copilot CLI | `--deny-tool='shell(git push --force)'`, never `--allow-all-tools` | Per-session flags |

The real boundary is GitHub: a write-role machine account and a `main` ruleset
that needs your approval. See [agent access](github-setup.md#agent-access-for-the-improvement-loop).

## Roll back

- Revert the merge commit through a pull request; projects pick it up on update.
- Hold one project back by pinning its dependency to a commit or tag in its
  `apm.yml`, then reinstall. Never edit `apm.lock.yaml` by hand.
- Never replace a published release; publish a corrected one.

## Limits

- No live link between checkout and installed copy; update after a merge.
- `apm find` traces project installs; for user scope, infer the package from
  the `kit-<topic>` skill name.
- A file test does not show a host follows new guidance; name the host and
  version you observed.
