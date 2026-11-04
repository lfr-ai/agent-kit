# VS Code workspace setup

Open the repository root as a single-folder workspace. The committed
[settings](../.vscode/settings.json), [tasks](../.vscode/tasks.json),
[debug configurations](../.vscode/launch.json),
[extension recommendations](../.vscode/extensions.json) and
[MCP servers](../.vscode/mcp.json) are the shared editor entry points. They do
not replace the repository verification gate (`task verify`).

## Start

1. Review the repository before granting Workspace Trust.
2. Install the recommended extensions you need; recommendations never install or
   disable anything. The dev container installs the same list except the
   host-side PowerShell and Dev Containers extensions.
3. Run **Tasks: Run Task > Bootstrap locked environment** (`task bootstrap`).
   It audits both locks, installs both environments and Git hooks, and on
   Windows registers `AGENT_KIT_DIR`. Do not bypass the audit with a direct sync.
4. Run **Python: Select Interpreter** and pick the root `.venv`.
5. Use **Run Build Task** for `task verify` and **Run Test Task** for all tiers.
   Other tasks: [developer tooling](devtools.md#entry-points).

## Workspace contract

The five workspace files are strict JSON. VS Code requires the `settings.json`
filename; renaming it to `settings.jsonc` breaks discovery.

| Area | Contract |
| --- | --- |
| Python and tests | Root `.venv` and root test discovery; no fixed Unix executable |
| Ruff | Native server, environment binary; `ruff.toml` is authoritative |
| Types | ty reads `ty.toml`; Mypy and Pylance are unwanted recommendations |
| Formatting | Ruff for Python, built-in JSON, declared YAML/TOML/Markdown providers, explicit ShellCheck actions |
| Files | UTF-8, LF and final newlines agree with EditorConfig |
| Templates | Associations add syntax only |
| Visibility | Exclude environments, builds and caches; skill mirrors leave text search but stay watched |
| Agents | Standard native discovery and AGENTS entry points |
| Personal settings | Shell paths, themes and UI preferences are not imported |
| Git, plugins, MCP | No smart commits, marketplace activation, automatic approvals or MCP auto-start |

Code actions name Ruff's fix and import providers. If an output channel reports
a bundled-version fallback, run bootstrap first. Do not copy tool options into
settings when the tool configuration owns them.

## Canonical versus generated files

Author under root or package `.apm` directories. Mirrored `.agents/skills` and
`.claude/skills` are read-only and out of text search but visible and watched.
`uv.lock`, `apm.lock.yaml` and `.coveragerc` stay searchable (excluding
`.coverage` and `.coverage.*`, not `.coverage*`). Read-only state and exclusions
are conveniences, not permissions; the repository gates remain authoritative.

## Debugging

| Configuration | Behavior |
| --- | --- |
| Debug current test file | pytest without xdist so breakpoints hit |

Debugging starts no servers or databases, opens no attach port, installs
nothing and publishes nothing.

## Agent boundaries

AGENTS and skill discovery stay enabled; mirrored Claude entry/hook loading is
disabled for VS Code Local; MCP autostart is `never`. Terminal rules set package
installers and runners (`pip install`, `uv add`, `uvx`, `npx` and similar) to
`false`, so they always need approval; see [dependency security](dependency-security.md).
`chat.agentFilesLocations` is not an isolation boundary; only
`chat.modeFilesLocations` is deprecated.

### Native discovery and menu

Every role renders as a flat file in `.github/agents/` and `.claude/agents/`.
VS Code scans only direct children of those folders, so a nested worker would
be undiscoverable ("Unknown agent ... will be ignored"). `agents:` entries match
the target's `name:` (case-sensitive), set to the role ID. Claude scans
recursively, but APM flattens file names, so flat output also avoids collisions.

Frontmatter by tier (checked 2026-11-03 against VS Code, GitHub Copilot and
Claude Code documentation):

| Tier | Copilot `tools` | Claude `tools` |
| --- | --- | --- |
| Verifier (analysis, review, check) | `read, search, execute, todo` | `Read, Grep, Glob, Bash` |
| Implementer | adds `edit` | adds `Edit, Write` |
| Coordinator | adds `agent`, plus an `agents:` list of workers | adds `Agent(a, b)` (main thread only) |

- Unknown Copilot tool names are dropped silently; omitting `tools` falls back
  to the picker's selection.
- `agents`, `handoffs` and `argument-hint` are unsupported by the github.com
  cloud agent.
- Primaries: `user-invocable: true`, `disable-model-invocation: true`. Workers:
  `user-invocable: false` (hidden but callable), `disable-model-invocation: false`.

The picker shows `kit-orchestrator` and `kit-debug`. Everything else
(`kit-devops-implementer`, `kit-infra-reviewer`, `kit-ddd`, `kit-sdd`,
`kit-deep-thinking`, `kit-test-author`, `kit-refactor`, ...) is a hidden worker.
All roles have an offline shell, which is not a sandbox. Canonical contract:
[native roles](../packages/shared/.apm/skills/kit-agent-runtime/references/native-roles.md).

No setting hides built-in or extension agents while keeping custom ones;
`chat.agent.enabled` disables agents entirely. To find an entry's source, use
**Configure Custom Agents** (hover) and **Chat > Diagnostics**. For an
extension agent, the operator may manage or disable that extension per
workspace; for a plugin, use the harness's plugin UI. This kit changes neither,
so a kit-only picker cannot be promised.

After source changes, run `python -m scripts.render_native` to audit drift,
then `--write`; reload the harness and test discovery and one worker call.
Configured servers are recorded in [MCP adoption](mcp-adoption.md).

## Verification and limits

Portable setup starts at the shared `kit-new-project` prompt: repository
hygiene, editor wiring, verification and setup docs through existing skills,
without installing a framework or changing user-global settings.
It then chains the standards prompts: `/kit-align-structure`, `/kit-align-ordering`, `/kit-align-typing`, `/kit-align-docstrings`, `/kit-centralize-cross-cutting`, `/kit-align-python-conventions`, `/kit-align-tests`, `/kit-reduce-cognitive-load`, `/kit-align-consistency`, `/kit-write-docs`, `/kit-align-agent-docs`.
The commit-message prompt and draft instruction use Conventional Commits and
never stage or commit.

Native contract checks pin interpreter, formatter/type-checker ownership, pytest
discovery and agent safeguards; task-wiring checks compare every editor task
with the Taskfile. Setting identifiers were checked against VS Code 1.141.0,
Ruff extension 2026.88.0 and ty extension 2026.80.0. Terminal activation is not
forced (`python-envs.terminal.autoActivationType` is machine-scoped).

These checks do not certify save actions, debugging, hosted permissions or all
extensions. In a fresh profile, open each file type, run the tasks and debug
entries, and inspect **Chat: Open Customizations**. Multi-root users put
window-scoped settings in the workspace file.

## Primary sources

- [Custom agents](https://code.visualstudio.com/docs/copilot/customization/custom-agents), [frontmatter reference](https://code.visualstudio.com/docs/agents/reference/custom-agent-file-reference), [subagents](https://code.visualstudio.com/docs/copilot/agents/subagents)
- [AI settings](https://code.visualstudio.com/docs/agents/reference/ai-settings), [settings and scopes](https://code.visualstudio.com/docs/configure/settings)
- [Agent-folder scan implementation](https://github.com/microsoft/vscode/blob/main/src/vs/workbench/contrib/chat/common/promptSyntax/utils/promptFilesLocator.ts#L660-L695)
- [Python settings](https://code.visualstudio.com/docs/python/settings-reference), [Python debugging](https://code.visualstudio.com/docs/python/debugging)
- [Ruff editor settings](https://docs.astral.sh/ruff/editors/settings/), [ty editors](https://docs.astral.sh/ty/editors/), [ty editor settings](https://docs.astral.sh/ty/reference/editor-settings/)
- [MCP servers](https://code.visualstudio.com/docs/agent-customization/mcp-servers), [agent skills](https://code.visualstudio.com/docs/agent-customization/agent-skills), [custom instructions](https://code.visualstudio.com/docs/agent-customization/custom-instructions)
