# Improve the kit from any project

Agent Kit is the one place reusable agent guidance lives. Projects consume it;
they do not keep local copies or workarounds. When a skill, instruction, prompt
or template misbehaves in a project, fix it once in this repository and every
project receives the change.

## Install once per machine

Install the packages you use every day at user scope. Nothing is copied into a
project repository.

```powershell
apm install -g lfr-ai/agent-kit/packages/shared
apm install -g lfr-ai/agent-kit/packages/backend
```

Packages do not depend on each other, so name each one: `shared` plus the
profile packages you need. Keep `ai`, `iac`, `workflows` and the IaC tool
features (`terraform`, `bicep`, `remote-access`) for the projects that use
them; every installed skill adds its description to every session.

Refresh and inspect:

```powershell
apm outdated -g
apm update -g --yes
```

### What user scope delivers

Observed with APM 0.33.0 installing `packages/shared` with `--target claude,copilot`:

| Primitive | Location |
| --- | --- |
| Skills | `~/.agents/skills/` and `~/.claude/skills/` |
| Instructions | `~/.claude/rules/` and `~/.copilot/instructions/` |
| Prompts | `~/.claude/commands/` and `~/.copilot/prompts/` |
| Native agent roles | Not delivered; they come from `agent-kit compose` or a project install |

APM warns that Claude commands drop the Copilot-only `agent:` field and that an
unpinned dependency follows the default branch. Both are expected here: the
lockfile records the exact commit, and `apm update -g` moves it deliberately.
Re-check this table after upgrading APM.

## Change a capability

Use `/kit-improve <what went wrong>` in the session where you saw the problem.
The [kit-improve skill](../packages/shared/.apm/skills/kit-improve/SKILL.md) does
the following:

1. Classifies the change; a fact about one project stays in that project.
2. Traces the installed file to its package with `apm find <path> --source`.
3. Verifies your kit checkout (origin and clean tree), then edits only its
   source under `.apm/` or `packages/*/.apm/`.
4. Reproduces the problem with a synthetic example and runs `task verify`.
5. Commits on a branch when you asked for the change, then waits for your
   approval before it pushes, opens the pull request and enables auto-merge.
6. You approve the pull request on GitHub; auto-merge completes when the
   required checks pass.

When the pull request merges, run `apm update -g` (or `apm update` in a project)
and confirm the installed file changed. Ideas you will not do now belong in an
issue using the *Capability change* form.

### Change classes

| Class | Lane | Version effect |
| --- | --- | --- |
| Project fact | The project's own instructions; never the kit | None |
| Trivial (typo, link, wording) | Pull request | Patch |
| Behavior (wrong steps, broken template) | Pull request with the failing prompt and expected result | Patch or minor |
| Contract (rename, remove, widen tools or policy) | Issue first, then a pull request labelled `breaking` | Minor while 0.x |
| Security | Private advisory, immediate patch release | Patch |

## Approval boundaries

Git is allowed in this repository under the rules in [AGENTS.md](../AGENTS.md):
read-only commands freely, branch and commit on request, and every push, pull
request or auto-merge only after you approve the exact command. Never the default
branch, force-push, rewritten pushed history, tags, releases or repository settings.

| Host | Enforcement in this repository | Limit |
| --- | --- | --- |
| Claude Code | `ask` and `deny` rules in `.claude/settings.json` | Prefix rules miss other spellings such as `git -C . push` |
| VS Code | `false` rules in `chat.tools.terminal.autoApprove` | They require approval; they cannot block, and `/yolo` bypasses them |
| GitHub Copilot CLI | Start sessions with `--deny-tool='shell(git push --force)'` and never `--allow-all-tools` here | Per-session flags, not repository files |

These are speed bumps. The boundary is on GitHub: the agent works as a
write-role machine account, and the `main` ruleset requires your approval before
anything merges. See [agent access](github-setup.md#agent-access-for-the-improvement-loop).

## Roll back

- Revert the merge commit through a pull request; projects pick it up on the
  next update.
- Hold one project back by pinning its dependency to a commit or tag in its
  `apm.yml`, then reinstall. Never edit `apm.lock.yaml` by hand.
- A published release is never replaced; publish a corrected one.

## Limits

- APM has no live link between a checkout and an installed copy; update after a
  merge to see the change.
- `apm find` traces project installs; for user scope, identify the package from
  the `kit-<topic>` skill name.
- A file test does not show that a host session follows new guidance; name the
  host and version you observed.
