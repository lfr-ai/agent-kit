# Hook protocols for the pre-tool guard

Hook formats differ by runtime and change between versions. Treat this page as a
map to the official references below, and confirm the exact host version before
relying on any field. A shared file location does not mean a shared payload.

## Payloads the guard reads

| Runtime | Event key | Tool name | Tool input | Notes |
| --- | --- | --- | --- | --- |
| Claude Code | `hook_event_name: "PreToolUse"` | `tool_name`, for example `Bash`, `PowerShell`, `Read`, `Edit`, `Write` | `tool_input` object | File tool paths arrive absolute; on Windows with backslashes |
| VS Code Local harness | `hook_event_name: "PreToolUse"` | `tool_name` (Local tool names) | `tool_input` object | Inspect the agent debug logs for exact Local tool names and schemas |
| Copilot CLI and cloud agent, `preToolUse` | none | `toolName`, for example `bash`, `powershell`, `view`, `edit`, `create` | `toolArgs`, may be a JSON string | `timestamp` is a number in this shape |
| Copilot CLI, PascalCase `PreToolUse` | `hook_event_name` | `tool_name` using Claude tool names | `tool_input` | Claude-style matcher semantics apply |

The guard collects strings from these input keys, case-insensitively, at any depth:

- Commands: `command`, `cmd`, `script`, `commandLine`, `command_line`.
- Paths: `file_path`, `filePath`, `file_paths`, `filePaths`, `path`, `paths`,
  `notebook_path`, `dirPath`, `dir_path`, `directory`, `target_file`, `old_path`,
  `new_path`, `source`, `destination`, `glob`, `include`, `uri`.
- Patches: `input`, `patch`, `diff` values contribute file names from
  `*** Add File:`, `*** Update File:`, `*** Delete File:`, and `*** Move to:` lines.

File contents in `content`, `new_string`, and similar fields are not scanned.
A payload that names the tool in both spellings with different values is rejected.

## Decisions the guard writes

The guard writes nothing for an unmatched call and exits `0`.

Claude Code and the VS Code Local harness (`--runtime claude` or `--runtime vscode`):

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "tool-guard deny: force-push: ..."}}
```

Copilot CLI and cloud agent (`--runtime copilot-cli`):

```json
{"permissionDecision": "ask", "permissionDecisionReason": "tool-guard ask: remote-publication: ..."}
```

With `--runtime auto` (the default), a payload with `toolName` or `toolArgs` gets
the Copilot CLI shape and a payload with `tool_name` gets the `hookSpecificOutput`
shape. This lets one `.github/hooks/*.json` file serve both Copilot CLI and the
VS Code Local harness, which maps the Copilot file format but sends its own payload.

## Exit codes across runtimes

| Guard exit | Claude Code | VS Code Local | Copilot CLI `preToolUse` |
| --- | --- | --- | --- |
| `0` with JSON | Fields apply | Fields apply | Fields apply |
| `0` without output | Normal permission flow | Normal permission flow | Default behavior |
| `2` with stderr | Blocks; stderr goes to the model | Blocks; stderr goes to the model | Denies the call |
| Crash or other code | Non-blocking unless `onFailure: "block"` | Warning, continues | Denies the call |
| Timeout | Non-blocking unless `onFailure: "block"` | Not documented as blocking | Always fail-open |

## Registering the hook

Copy the guard to a consumer-owned directory first; do not point a hook at a skill
installation directory, which is generated and may move.

- Copilot CLI, cloud agent, and VS Code Local: copy
  [copilot-hooks.json.template](../assets/copilot-hooks.json.template) to
  `.github/hooks/tool-guard.json`. The version-1 file uses `bash` and `powershell`
  command fields and `timeoutSec`. Cloud agent honors only `bash` or `command`.
  VS Code Local requires `chat.useHooks` and a trusted workspace.
- Claude Code: merge
  [claude-settings-hooks.json.template](../assets/claude-settings-hooks.json.template)
  into `.claude/settings.json`. It uses exec form (`command` plus `args`) so paths
  with spaces need no quoting, matches every tool with `*`, and sets
  `onFailure: "block"`. Older Claude Code versions may not support `args` or
  `onFailure`; check the installed version and use shell form with a quoted path if
  needed. On Windows, `python3` may be `python` or `py -3`.
- VS Code Local also reads `.claude/settings.json` only when `chat.useClaudeHooks`
  is on, and then ignores matchers. Register the guard in one place per harness to
  avoid running it twice.

This repository does not activate either template. Activation is a consumer
decision recorded with its own tests.

## Verifying a registration

1. `python .agents/hooks/tool_guard.py check-policy .agents/hooks/tool_guard_policy.json`
2. Pipe a synthetic payload of each shape into the `hook` subcommand and compare the
   output with the tables above.
3. In each runtime, run one harmless command, one `ask` command, and one `deny`
   command in a disposable repository. Record host version and shown reason.
4. Rename the policy temporarily to confirm the failure path blocks as configured.

## Sources

- [Claude Code hooks reference](https://code.claude.com/docs/en/hooks)
- [GitHub Copilot hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference)
- [VS Code agent hooks](https://code.visualstudio.com/docs/agent-customization/hooks)
- [VS Code Local hooks reference](https://code.visualstudio.com/docs/agents/reference/hooks-reference)
