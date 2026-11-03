# Bypass policy, CI enforcement and agent hooks

A Git hook is advisory for whoever holds the repository: the committer can
remove, skip or never install it. Policy therefore has three parts: what
people and agents may do locally, what CI enforces regardless, and how the two
hook layers (Git hooks and agent tool hooks) differ.

## What a bypass skips

| Mechanism | Skips | Does not skip |
| --- | --- | --- |
| `git commit --no-verify` (`-n`) | `pre-commit` and `commit-msg` hooks | `prepare-commit-msg`, post-commit hooks |
| `git push --no-verify` | `pre-push` hook | server-side checks, branch protection, push protection |
| `SKIP=<hook-id>[,<hook-id>]` with pre-commit | only the named hooks | every other hook |
| uninstalling hooks, a different clone, a different tool (web editor, API) | all local hooks | everything enforced by CI or the server |

Because every row can be done without anyone noticing, a local hook is never
the control for a rule that must hold.

## Policy

| Actor | Rule |
| --- | --- |
| Contributor | skip a hook only with a stated reason and the narrowest scope (`SKIP=<id>` before `--no-verify`); say so in the pull request; CI still decides |
| Agent | never run `--no-verify`, `-n`, `SKIP=`, hook uninstalls, `core.hooksPath` changes or a baseline rewrite to get past a failing hook; fix the cause, or stop and report that the hook or its tool is broken |
| Maintainer | owns the hook configuration; changes to it are reviewed like code; a bypass that recurs means the hook is too slow or wrong and needs fixing |
| CI | re-runs every hook's check on all files with the same pinned tools and is a required status check |

For agents, state the rule in the agent instructions and, where the runtime
supports it, back it with a pre-tool hook that denies commit and push commands
carrying bypass flags. That hook inspects literal command text only, so
indirection can evade it; the instruction and review remain necessary.

## CI as the enforcement boundary

1. List each rule that must hold on the main branch (formatting, lint, types,
   tests, secrets, commit title, lockfile, license).
2. Map each to a required CI check on the same definition the hook uses.
3. Require those checks in branch protection (or a ruleset) so a merge needs
   them to pass, and require review for changes to hook and CI configuration.
4. Enable hosting-platform secret scanning and push protection as an
   independent server-side layer.
5. Verify the mapping periodically: introduce a deliberate failure on a scratch
   branch with hooks skipped, and confirm CI blocks the merge.

## Git hooks versus agent pre-tool hooks

| Aspect | Git hooks | Agent pre-tool hooks |
| --- | --- | --- |
| Run by | Git, on commit and push | the agent runtime, before a tool call executes |
| Sees | staged files, the message file, refs being pushed | the literal tool name and input of one call |
| Purpose | keep bad content out of commits | stop or ask before an agent runs a risky command |
| Skipped by | `--no-verify`, `SKIP`, no install | a tool or syntax the policy does not name; indirection; runtime settings that disable hooks |
| Failure semantics | a non-zero exit aborts the operation | Copilot command hooks deny on a crash or non-zero exit but fail open on timeout; Claude Code blocks only on exit code 2, so other failures let the call run |
| Not a sandbox | right: CI is the boundary | right: native approvals, least-privilege identities and branch protection remain |
| Configuration home | `.pre-commit-config.yaml` or `lefthook.yml` | the runtime's hook files, delivered by the package manager for agent runtimes |

Practical consequences:

- An agent hook can deny `git commit --no-verify` before Git ever sees it; a Git
  hook can reject a secret that an agent hook never inspected. Keep both, with
  different jobs.
- Do not move a rule from CI into either layer to save time. Both can be
  skipped; CI cannot be skipped by the committer.
- Give agent hooks a short explicit timeout, because a timeout is not a denial.
- Test both layers against synthetic inputs, and record that a file check is
  not evidence of a live runtime session.

## Recording a legitimate bypass

Use the [review record](../assets/git-hooks-review.md.template) or the pull
request: hook id, reason, scope, who approved, the follow-up that removes the
need, and the CI result. A bypass without a recorded reason is a finding.

## Primary sources

- Git, [githooks](https://git-scm.com/docs/githooks)
- Git, [git-commit](https://git-scm.com/docs/git-commit)
- Git, [git-push](https://git-scm.com/docs/git-push)
- pre-commit, [documentation](https://pre-commit.com/)
- GitHub, [About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- GitHub, [About push protection](https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection)
- GitHub Copilot, [Hooks configuration](https://docs.github.com/en/copilot/reference/hooks-configuration)
- Claude Code, [Hooks reference](https://code.claude.com/docs/en/hooks)
