# Agent guards

Guards are small local programs that a runtime calls at a hook point. This skill
documents three: a pre-tool guard, a license guard, and a review-package gate. They are
**defense in depth**. They are not an authorization boundary, not a sandbox, and
not a substitute for native approval modes, permission rules, or managed policy.

The pre-tool guard is delivered by the `shared` package as an APM hook, so every
profile carries it. The license guard and review package stay opt-in assets that a
consumer copies, reviews and registers in a configuration file they own.

## Delivered Git guard

`shared` ships `git-guard.json`, a `preToolUse` hook that runs `tool_guard.py` with
`git-guard.policy` from its `hooks/` directory. It never approves a
call, documents its bypasses, and is not a sandbox: a project still relies on
native controls, and the guard catches common mistakes earlier with a clearer reason.

## Threat model

| Threat | Example | Guard helps? | Primary control |
| --- | --- | --- | --- |
| Accidental destructive command | recursive delete of a root, force push | Yes, for literal spellings | Native approval prompt, branch protection |
| Secret file read | agent opens a dotenv or private key file | Yes, for named paths | Permission deny rules, secret store, file mentions off |
| Prompt-injected instruction from fetched content | page text tells the agent to pipe a script to a shell | Partly: blocks common literal patterns | Native approval, network allow lists, sandbox |
| Verification bypass | skipping commit hooks, disabling TLS checks | Yes, for known flags | CI enforces checks server side |
| Hook tampering | agent edits its installed hook | Denies named file-edit tools | Code review, protected branches, workspace trust |
| Deliberate evasion by a capable agent | variables, aliases, generated scripts, encoded payloads | No | Sandbox, least-privilege tools, review |
| Malicious MCP server or extension | tool with a new name and arbitrary behavior | Only if the policy names it | Do not install untrusted servers; native tool approval |
| Hallucinated or malicious package | agent installs an unreviewed name (slopsquatting) | Denies literal installers, syncing and downloading runners | Audited locks, native permissions and dependency review in CI |
| Database damage | `DROP TABLE`, migration, Redis flush | Denies named SQL mutations, migration commands and write tools | Read-only identities, isolated test databases, backups and recovery drills |
| License drift in dependencies | new transitive dependency under a denied license | Yes, at check time | Dependency review in CI, legal review |

The pre-tool guard sees only the tool name and the literal tool input that the
runtime passes to the hook. It cannot see what a script will do once it runs,
what a variable expands to, or what a symbolic link points at.

## What each guard does

- `tool_guard.py` (the delivered hook engine) reads one pre-tool hook payload on stdin,
  evaluates it against a policy such as
  [the policy template](../assets/tool_guard_policy.json.template),
  and prints a `deny` or `ask` decision in the runtime's JSON shape. An unmatched
  call prints nothing, so the runtime's normal permission flow decides.
- [license_guard.py](../assets/license_guard.py) checks installed Python distribution
  metadata against [an allowlist](../assets/license_allowlist.json.template). See the
  [license guard reference](license-guard.md).
- [review_package.py](../assets/review_package.py) assembles a review package and
  fails when evidence is missing or failing. See
  [subagent-driven development](subagent-driven-development.md).

## Git scope

`git-guard.policy` uses the same engine as every other policy and is always on.

- **Everywhere:** deny hook-bypass flags (`--no-verify`, `-n`, abbreviations),
  unsafe options, shell composition, Git metadata writes (including through file
  tools), non-read-only GitHub CLI use, and file-tool edits to installed hook and
  settings files.
- **Outside the kit checkout:** only `diff`, `status`, `log`, `show`, `blame`,
  `ls-files` and `rev-parse` are available; staging, commits, branches, fetch, pull
  and push belong to the operator. The guard's own files cannot be edited or
  named in shell commands.
- **Inside the checkout named by `AGENT_KIT_DIR`** (compared with the hook payload's
  `cwd`): staging, commits, `switch`, `restore`, `fetch`, `pull` and an explicit
  `git push origin feature/example` pass to native authorization. Force pushes,
  implicit targets, known default names (`main`, `master`, `trunk`, `HEAD`),
  refspecs, tags, rebase and reset stay denied. Confirm the remote's actual default
  branch separately; it can have another name. The guard sources can be maintained.
  An unset or empty `AGENT_KIT_DIR` never matches, so the kit exception is opt-in per
  machine. The variable comes from the operator's environment and the `cwd` from the
  host, not from the agent. Both must identify existing absolute directories;
  symlinks are resolved before containment checks. Registration is documented in the repository's
  `scripts/register_checkout.ps1`.

Subcommand matches require a complete token, so an alias such as `diff-custom` is
not accepted as `diff`. Output-like long flags and attached `-o`/`-c` forms are
conservatively denied, including some harmless options.

Rules carry optional `only_in` / `except_in` fields naming an upper-case
environment variable that holds a directory; they are mutually exclusive.

```text
python tool_guard.py check-policy git-guard.policy
python tool_guard.py explain --policy git-guard.policy --tool Bash --command "git push" --cwd .
```

The second command must report `deny` and exit 1. A registered `hook` handler
instead emits the runtime's denial JSON and exits 0; exit 0 does not mean allow.
Test both the standalone script and a real host session before relying on it.
OS-level write restrictions on Git metadata, inaccessible credentials and hosted
rulesets are required for a stronger boundary.

## Safety rules delivered with Git restrictions

These are deny rules, not optional approval prompts:

| Category | Examples denied | Safe neighbor |
| --- | --- | --- |
| Secret files | `.env`, private keys, cloud credentials, Docker credential config | Sanitized `.env.example` |
| Dependency installation | `pip install`, `uv sync`, `uv run` without `--no-sync`, `bun install`, downloading runners | `uv add --no-sync`, `uv audit --locked`, `uv run --locked --no-sync pytest` |
| Recursive deletion and disks | `rm -rf`, `Remove-Item -Recurse`, formatting devices | Deleting one approved leaf file |
| Remote or hidden execution | Download piped to shell, encoded PowerShell | Downloading source for review |
| Database writes | SQL write/DDL literals, Alembic migrations, Redis/Mongo writes, named database execution tools | SELECT with a read-only identity |
| Verification bypass | TLS/certificate verification disabled | Normal verified HTTPS |
| Secrets and privilege | Dumping all environment variables, `sudo`, `chmod 777` | Inspecting an approved non-secret variable |

This hook does not remember a successful dependency audit. Installation stays
operator-only: audit the changed locks, then perform a locked sync outside the
agent. MCP server startup is host-controlled, not a shell tool call; exact server
pins and host consent remain separate requirements.

Database patterns are deliberately conservative, not a SQL parser. They may also
match SQL inside a test fixture or documentation command. Generic query tools,
stored procedures and unknown tool names may evade them; read-only database
roles, environment isolation and backups are the actual boundary.

## Policy model

Each rule has an `id`, a `decision` (`deny` or `ask`), a `match` target, a
`pattern` (Python `re.search`, case-insensitive), a `reason`, and an optional
`tools` pattern that must fully match the tool name. Precedence is deny, then ask,
then no output. The guard never emits `allow`, because an `allow` from a hook can
skip the runtime's own approval prompt.

| Target | What is matched |
| --- | --- |
| `tool` | The casefolded tool name |
| `command` | Each whole command view, so pipelines such as download-then-shell match |
| `segment` | Each command piece split on `;`, `&`, `&&`, `\|\|`, `\|`, newlines, parentheses, `$(`, and backticks |
| `path` | Each named path field, each patch file header, and each token of each command segment |

Normalization before matching:

- Unicode compatibility normalization, removal of invisible format characters, casefolding.
- Line continuations for POSIX shells, PowerShell, and `cmd` are joined.
- Three spellings of every command are checked: as written, with quotes, backticks
  and carets removed, and additionally with backslashes removed.
- Paths use forward slashes, collapse repeated separators, resolve `.` and `..`
  lexically, drop a `file://` prefix, drop NTFS stream suffixes such as `:$DATA`,
  and drop trailing dots and spaces that Windows ignores.

Top-level policy fields:

| Field | Default | Meaning |
| --- | --- | --- |
| `schema_version` | required, `1` | Closed schema; unknown fields are errors |
| `fail_mode` | `closed` | What happens when a call cannot be evaluated |
| `mode` | `enforce` | `audit` reports would-be decisions on stderr and emits nothing |
| `max_input_bytes` | 2 MiB | Larger payloads are evaluation errors, never truncated |

### Fail-open versus fail-closed

The default is **fail-closed**: malformed JSON, an oversize payload, a missing tool
name, conflicting duplicate fields, or an unreadable policy makes the guard exit
`2` with the reason on stderr. All three runtimes treat exit `2` from a pre-tool
hook as a block. When the policy file itself cannot be loaded, the `--fail-mode`
flag decides (default `closed`).

Set `"fail_mode": "open"` only for a time-boxed audit rollout, when a broken guard
must not stop work. Runtime behavior around the guard also matters:

- Claude Code: a hook that crashes, cannot start, or times out does not block by
  default. Set `onFailure` to `block` on the command hook (Claude Code v2.1.295 or
  later), as the [Claude template](../assets/claude-settings-hooks.json.template) does.
- Copilot CLI: crashes and non-zero exits deny a `preToolUse` call, but timeouts are
  always fail-open, including for policy hooks.
- VS Code Local harness: exit `2` blocks; other non-zero exits warn and continue.

## Known bypasses and false positives

Document these to every adopter. The guard does not try to close them.

- Indirection: shell variables, aliases, functions, `eval`, command substitution
  built at runtime, and environment expansion.
- Generated code: the agent writes a script or test that performs the action, then
  runs it with an innocuous command.
- Interpreters: `python -c`, `node -e`, PowerShell script blocks, and build tools
  that run arbitrary tasks.
- Encodings the policy does not name, compression, and character tricks beyond
  compatibility normalization.
- Tools the policy does not name, including MCP tools with new names, and search
  tools that read a whole directory that contains a secret file.
- Files attached by the user through mentions, which some runtimes insert without a
  tool call.
- Symbolic links and junctions: path rules compare names, not resolved targets.
- Timeouts in Copilot CLI and, without `onFailure`, crashes in Claude Code.
- False positives: a commit message that mentions a forbidden flag, a heredoc that
  contains a secret file name, or a project `.npmrc` without tokens. Tune patterns
  or rely on `ask` instead of `deny`.

## Layering

1. Native first: configure approval modes, permission deny and ask rules, sandboxing,
   and workspace trust in each runtime. These are the enforcement layer.
2. Server side: branch protection, required reviews, CI checks, and secret scanning
   cannot be bypassed by a local agent.
3. Guard: catches literal high-risk spellings early with a clear reason, and records
   would-be decisions during rollout.
4. Review: the review package and reviewer roles catch what slipped through.

A guard `ask` never weakens a native deny. In Claude Code, permission deny and ask
rules are evaluated regardless of the hook result. In Copilot cloud agent and CLI
autopilot, `ask` is treated as deny because nobody can answer.

## Package installation

Agents should not install packages ad hoc. Package hallucination is repeatable,
and attackers register hallucinated names. Route every dependency through a
reviewed manifest and lockfile change instead:

1. Change the manifest and lock without installing, for example
   `uv add --no-sync <name>`.
2. Audit the changed lock before syncing it: known vulnerabilities, wheel-only
   installs, and lock hashes. Then install with the locked command
   (`uv sync --locked`, `npm ci`).
3. Check installed licenses, then let pull-request dependency review and CI repeat
   both audits server side.

Enforce the first step natively. Claude Code rules such as `Bash(uv add *)`,
`Bash(pip install *)`, `Bash(npx *)` and `Bash(uvx *)` in `permissions.deny` block
the literal commands; VS Code `chat.tools.terminal.autoApprove` rules set to
`false` always require approval for matching subcommands, even when another rule
would auto-approve them. Both are matched against command text and can be
bypassed through other spellings, interpreters, or generated scripts, so CI audits
remain the authoritative boundary. Pair them with a sandbox or network allowlist
where the host supports one. The optional baseline template uses `ask` for dependency installation. The
always-delivered safety policy is stricter: installation is operator-only.

## Rollout

1. Copy the delivered `tool_guard.py` and the policy template into a consumer-owned directory such
   as `.agents/hooks/`, rename the policy to `tool_guard_policy.json`, and review
   every rule with the repository owner.
2. Run `python .agents/hooks/tool_guard.py check-policy .agents/hooks/tool_guard_policy.json`.
3. Exercise rules without a runtime:
   `python .agents/hooks/tool_guard.py explain --policy <policy> --tool Bash --command "git push --force"`.
4. Set `"mode": "audit"`, register the hook (see [hook protocols](hook-protocols.md)),
   and pass `--audit-log` to collect would-be decisions. The log stores a SHA-256 of
   the input, never the command text.
5. Review audit results, tune false positives, then switch to `enforce`.
6. Record native host results in the [certification worksheet](../assets/certification.md.template).

## Testing

- Unit: run `tool_guard.py --self-test`, then table tests of deny, ask, and no output
  for each runtime payload shape, malformed and oversize input, and policy errors.
- Host: in a disposable repository, trigger one allowed, one asked, and one denied
  call per runtime and record the runtime version and the shown reason.
- Regression: when a bypass or false positive is found, add a case before changing
  the pattern.

A passing file test does not certify a native IDE, CLI, or cloud session.

## Sources

- [Claude Code hooks reference](https://code.claude.com/docs/en/hooks)
- [Claude Code permissions](https://code.claude.com/docs/en/permissions)
- [Claude Code sandboxing](https://code.claude.com/docs/en/sandboxing)
- [VS Code approvals and terminal auto-approval](https://code.visualstudio.com/docs/agents/run/approvals)
- [Package hallucinations by code-generating LLMs](https://arxiv.org/abs/2406.10279)
- [GitHub Copilot hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference)
- [VS Code agent hooks](https://code.visualstudio.com/docs/agent-customization/hooks)
- [VS Code Local hooks reference](https://code.visualstudio.com/docs/agents/reference/hooks-reference)
- [VS Code agent tools](https://code.visualstudio.com/docs/agents/run/tools)
- [OWASP LLM01 prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- [OWASP LLM06 excessive agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
