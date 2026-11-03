# Commit messages and secret scanning

Two hook families act on what a commit contains: the message and the staged
content. Both are cheap to check locally and must be re-checked in CI.

## Conventional Commit messages with commitizen

Conventional Commits give a message the shape
`<type>[optional scope][!]: <description>`, so the next version and a changelog
draft can be derived from history. commitizen validates the shape at the
`commit-msg` stage.

```yaml
repos:
  - repo: local
    hooks:
      - id: commitizen
        name: Conventional Commit message
        entry: uv run --locked cz check --allow-abort --commit-msg-file
        language: unsupported
        stages: [commit-msg]
```

- The `commit-msg` hook receives the path of the message file as its argument;
  pre-commit appends it to `entry`. The stage must be installed
  (`default_install_hook_types` includes `commit-msg`), or the hook never runs.
- `--allow-abort` lets an aborted empty message pass instead of failing.
- `commit-msg` can be skipped with `--no-verify`. Validate the range in CI
  (`cz check --rev-range origin/main..HEAD`) or, under squash merges, validate
  the pull-request title, because only the title becomes the commit.
- Keep one commitizen configuration file (`.cz.toml`, `cz.toml` or the
  `[tool.commitizen]` table). The `kit-release` skill's conventional-commits
  reference and commitizen template cover the options.
- Messages describe the effect in the imperative: `fix(orders): reject negative
  quantities`, not `fixed bug`.
- Footers follow Git trailer format (`Refs: #123`, `Co-authored-by: ...`); do not
  strip trailers that tooling adds.

### Agent-written messages

Agents follow the same rule, but each host reads it from a different place:

| Host | Where the rule lives |
| --- | --- |
| Copilot CLI, Claude Code, VS Code agents | One line in `AGENTS.md` (Claude reads it through the `CLAUDE.md` import) |
| VS Code "Generate commit message" | `github.copilot.chat.commitMessageGeneration.instructions` in `.vscode/settings.json` |

```jsonc
"github.copilot.chat.commitMessageGeneration.instructions": [
  { "text": "Write a Conventional Commits 1.0 message: '<type>(<scope>)[!]: <imperative summary>', at most 72 characters." }
]
```

Editor settings do not reach CLI agents, so keep the `AGENTS.md` line. The
`commit-msg` hook still rejects a bad message from any author; instructions
only make the first attempt right.

Other message hooks:

- `prepare-commit-msg` edits the message (for example to insert a ticket key) and
  is not suppressed by `--no-verify`; it must not be used as a replacement for
  validation.
- A message hook cannot know the final squashed message; do not duplicate the
  rule set in two tools.

## Choosing the scanner

| Question | detect-secrets | gitleaks |
| --- | --- | --- |
| Primary strength | audited baseline of known findings so the hook reports only new ones | broad rule set and scanning of Git history |
| Pre-commit integration | hook repository with `--baseline` | hook repository (native binary or a container id) |
| History scan | not its focus | `gitleaks git` over the repository history |
| Skip locally | `SKIP=detect-secrets` | `SKIP=gitleaks` |
| False-positive handling | baseline entries, inline allowlist comment | allowlist rules in its configuration |
| Pick it when | working-tree checks with a reviewed baseline are the main need | history scans and detection breadth are the main need |

Decision rules:

1. Choose one primary working-tree scanner, run it at `pre-commit` against
   staged files and in CI against all files. Do not enable two scanners with the
   same coverage without a documented difference.
2. Add a history scan (gitleaks) as a scheduled or `manual` job when old leaks
   matter; it is too slow for every commit.
3. Hosting-platform push protection is a separate boundary: it blocks known
   provider token formats on push, regardless of local hooks.
4. Keep the baseline in the repository, review changes to it like code, and
   treat an added entry as a claim that something is not a secret.
5. Regenerating a baseline is a fix action, never part of a check-only gate: a
   gate that rewrites the baseline can silently accept a new secret.

Testing the scanner safely:

- Seed an obviously fake value of the right shape in a scratch file, confirm the
  hook rejects it, then remove it. Never paste a real credential, and never
  commit the seed.
- Test fixtures use clearly fake placeholders (`test-token`, `example.invalid`)
  so scanners and reviewers can tell them apart from real values.

When a secret has been committed or pushed, rotate it first. Removing it from
history is secondary; the `kit-verify-change` skill's secrets-scanning
reference has the full response steps.

## Primary sources

- Conventional Commits, [specification 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)
- commitizen, [documentation](https://commitizen-tools.github.io/commitizen/)
- Git, [githooks](https://git-scm.com/docs/githooks)
- detect-secrets, [project documentation](https://github.com/Yelp/detect-secrets)
- gitleaks, [project documentation](https://github.com/gitleaks/gitleaks)
- GitHub, [About push protection](https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection)
- pre-commit, [documentation](https://pre-commit.com/)
- VS Code, [custom instructions for generated content](https://code.visualstudio.com/docs/copilot/customization/custom-instructions)
