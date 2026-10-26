# Opt-in agent guards

Guards are small local programs that a runtime calls at a hook point. This skill
ships three: a pre-tool guard, a license guard, and a review-package gate. They are
**defense in depth**. They are not an authorization boundary, not a sandbox, and
not a substitute for native approval modes, permission rules, or managed policy.

Nothing here is active until a consumer copies the assets, reviews the policy, and
registers the hook in a runtime configuration file they own.

## Why opt-in

An earlier toolkit decision removed a deny-everything hook stub because shipping it
would have implied a safety property it did not have. The guards below keep that
lesson: they never approve a call, they document their bypasses, and the toolkit
does not install them. A project that adopts them still relies on native controls
for enforcement and uses the guard to catch common mistakes earlier and with a
clearer reason.

## Threat model

| Threat | Example | Guard helps? | Primary control |
| --- | --- | --- | --- |
| Accidental destructive command | recursive delete of a root, force push | Yes, for literal spellings | Native approval prompt, branch protection |
| Secret file read | agent opens a dotenv or private key file | Yes, for named paths | Permission deny rules, secret store, file mentions off |
| Prompt-injected instruction from fetched content | page text tells the agent to pipe a script to a shell | Partly: blocks common literal patterns | Native approval, network allow lists, sandbox |
| Verification bypass | skipping commit hooks, disabling TLS checks | Yes, for known flags | CI enforces checks server side |
| Hook or workflow tampering | agent edits a hook file that later runs automatically | Asks before known write tools touch it | Code review, protected branches, workspace trust |
| Deliberate evasion by a capable agent | variables, aliases, generated scripts, encoded payloads | No | Sandbox, least-privilege tools, review |
| Malicious MCP server or extension | tool with a new name and arbitrary behavior | Only if the policy names it | Do not install untrusted servers; native tool approval |
| Hallucinated or malicious package | agent installs a plausible but unreviewed name (slopsquatting) | Yes: `dependency-install` asks before literal installers and package runners | Native deny rules for installers, reviewed lockfile, dependency review and lock audit in CI |
| License drift in dependencies | new transitive dependency under a denied license | Yes, at check time | Dependency review in CI, legal review |

The pre-tool guard sees only the tool name and the literal tool input that the
runtime passes to the hook. It cannot see what a script will do once it runs,
what a variable expands to, or what a symbolic link points at.

## What each guard does

- [tool_guard.py](../assets/tool_guard.py) reads one pre-tool hook payload on stdin,
  evaluates it against [the policy template](../assets/tool_guard_policy.json.template),
  and prints a `deny` or `ask` decision in the runtime's JSON shape. An unmatched
  call prints nothing, so the runtime's normal permission flow decides.
- [license_guard.py](../assets/license_guard.py) checks installed Python distribution
  metadata against [an allowlist](../assets/license_allowlist.json.template). See the
  [license guard reference](license-guard.md).
- [review_package.py](../assets/review_package.py) assembles a review package and
  fails when evidence is missing or failing. See
  [subagent-driven development](subagent-driven-development.md).

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
where the host supports one. The template's `dependency-install` rule asks rather
than denies, because an approved dependency change is a normal operator action.

## Rollout

1. Copy `tool_guard.py` and the policy template into a consumer-owned directory such
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
