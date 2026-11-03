# VS Code workspace setup

Open the repository root as a single-folder workspace. The committed
[settings](../.vscode/settings.json), [tasks](../.vscode/tasks.json),
[debug configurations](../.vscode/launch.json) and
[extension recommendations](../.vscode/extensions.json), and
[MCP server definitions](../.vscode/mcp.json) are the shared editor entry
points. They do not replace the CLI completion gate.

## Start

1. Review the repository before granting Workspace Trust.
2. Install the recommended extensions you need. Recommendations do not silently
   install extensions or disable ones already installed. The dev container
   installs the same list except two host-side extensions (PowerShell and Dev
   Containers), which belong on the machine that opens the container.
3. Run **Tasks: Run Task > Bootstrap locked environment**, or `task bootstrap`.
   Bootstrap audits the Python and JavaScript locks before installing either
   environment and then installs Git hooks. This is an explicit action, not a
   folder-open task; do not bypass the audit with a direct dependency sync.
   On Windows it also registers `AGENT_KIT_DIR` for future sessions. New
   integrated terminals in this checkout receive the workspace path directly.
4. Run **Python: Select Interpreter** and select the repository's `.venv`.
   The portable default points to the directory, so Windows and Unix do not need
   different executable paths. Changing this default does not replace a previous
   workspace interpreter selection.
5. Use **Run Build Task** for `task verify`, or **Run Test Task** for all test
   tiers. The other editor tasks cover bootstrap, types, lint, formatting,
   pre-commit, APM smoke, the tox matrix, checkout registration and an interactive
   Conventional Commit prompt. Use `task verify -- <gate>` or the owning CLI for
   focused checks; editor tasks do not duplicate the complete gate inventory.

## Workspace contract

The workspace setup is scoped to this Python CLI and capability library. The
five workspace files remain strict JSON with blank-line groups, compatible
with the repository's existing parsers; JSONC section comments are not required.
VS Code requires the `settings.json` filename even though its parser accepts
JSONC. Do not rename it to `settings.jsonc`: workspace discovery would break.
The strict subset used here needs no `check-json` exclusion.

| Area | Contract |
| --- | --- |
| Python interpreter and tests | Root `.venv`, root test discovery and the configured workspace interpreter; no backend subfolder or fixed Unix executable |
| Ruff | Native server and environment-resolved binary; repository `ruff.toml` remains authoritative, without duplicated rule lists or line-length arguments |
| Type checking | ty reads `ty.toml`; Pylance is not a second language server |
| Language formatting | Ruff for Python, built-in JSON formatting, declared YAML/TOML/Markdown providers and explicit ShellCheck actions |
| File conventions | UTF-8, LF and final/trailing-newline settings agree with EditorConfig |
| Templates | File associations expose syntax without turning resource examples into another application/toolchain |
| Visibility and watching | Exclude environments, builds and caches; omit skill mirrors from ordinary text search without hiding or disabling native discovery watches |
| Agent setup | Standard native discovery and existing AGENTS entry points; no deprecated duplicate-location roster |
| Terminal and appearance | Machine shell paths, themes and personal UI preferences are not imported |
| Git, plugins and MCP | No smart-commit changes, marketplace activation, automatic approvals or MCP auto-start; the reviewed remote connections are confined to the MCP manifest |

The Python code actions explicitly name Ruff's fix and import providers.
The editor uses the locked environment's Ruff/ty when available; run bootstrap
first and inspect their output channels if a bundled-version fallback is reported.
Do not copy formatter/type-checking options into workspace settings when the
owning tool configuration already defines them.

## Canonical versus generated files

Author under root/package `.apm` directories. Mirrored `.agents/skills` and
`.claude/skills` are read-only and excluded from ordinary text search, but remain
visible and watched so native discovery can observe refreshed capabilities.
Their parent directories are not hidden: knowledge, agentic setup, native
settings and guards remain inspectable.

`uv.lock`, `apm.lock.yaml` and `.coveragerc` remain searchable. Cache exclusions
use `.coverage` and `.coverage.*`, not `.coverage*`, which would also hide the
coverage configuration.

Editor read-only state and exclusions are convenience features, not filesystem
permissions or a sandbox. Existing source/provenance/native-role checks remain
the actual repository gates. Other harnesses and external tools can still see
parent, user or plugin capabilities.

## Debugging

- **Check canonical toolkit** debugs the real `agent_kit` module.
- **Compose a profile into build/** asks for the profile and a new output
  directory. The CLI still refuses existing destinations; choose another name
  instead of deleting a consumer or weakening the no-overwrite guard.
- **Debug current test file** runs pytest without xdist so breakpoints stay in
  the expected test process.

Debugging uses the selected workspace interpreter. It does not inject source
paths, start databases/web servers, expose an attach port, install dependencies,
publish, or deploy. No FastAPI, browser or frontend runtime is configured for a
repository that has no such application.

## Agent boundaries

Keep AGENTS/skill discovery enabled, mirrored Claude entry/hook loading disabled
for VS Code Local, and MCP autostart at `never`. Workspace terminal rules set
package installers and package runners (`pip install`, `uv add`, `uvx`, `npx` and
similar) to `false`, so they always require approval even when another rule
would auto-approve them; see [dependency security](dependency-security.md).
Native Claude keeps its own adapter. Current Copilot harness discovery differs
from Local. The supported `chat.agentFilesLocations` setting is not an isolation
boundary and is not inherited by other Copilot clients; this workspace uses
standard native folders instead. Only the older `chat.modeFilesLocations` is
deprecated.

### Native discovery and menu

The renderer emits every role as a flat file directly in `.github/agents/` and
`.claude/agents/`; there is no `subagents/` folder. VS Code's default
`chat.agentFilesLocations` scan reads only direct children of `.github/agents`
(and `.claude/agents`), unlike its recursive instruction-file scan, so a nested
worker would be undiscoverable and a coordinator's `agents:` entry would fail with
"Unknown agent ... will be ignored". `agents:` entries are matched against the
`name:` frontmatter of the target file (case-sensitive), which the renderer sets to
the role ID. Claude Code scans `.claude/agents` recursively, but APM flattens agent
file names to the stem on deployment, so same-named files in subfolders would
collide; flat output avoids both problems.

Copilot frontmatter per tier (checked against the VS Code custom-agent and
file-reference pages, GitHub Copilot custom-agent docs and the Claude Code
sub-agent docs on 2026-11-02):

- `tools` uses the Copilot aliases `read`, `search`, `edit`, `execute`, `agent`,
  `web` and `todo`. Verifiers (every analysis, review and check role) get
  `read, search, execute, todo` for offline inspection; implementers get `read, search, edit, execute,
  todo`; coordinators add `agent`. Unknown tool names are silently dropped, so a
  Claude-style name in a Copilot file would lose that tool; omitting `tools`
  would instead fall back to whatever the picker has enabled.
- `agents:` is written only on coordinators and lists exact worker names. The key
  is omitted elsewhere (Local treats an omitted list as "all agents", but roles
  without the `agent` tool cannot delegate anyway). `agents`, `handoffs` and
  `argument-hint` are not supported by the github.com cloud agent.
- Primaries set `user-invocable: true` and `disable-model-invocation: true`.
  Workers set `user-invocable: false`, which hides them from the picker while
  keeping them available as subagents, and `disable-model-invocation: false`
  (the replacement for the deprecated `infer`). The two flags are independent.
- Claude files carry `name`, `description` and a scoped `tools` string
  (`Read, Grep, Glob`, plus `Bash` and `Edit, Write` by tier). The `Agent(a, b)`
  allowlist on coordinators only takes effect when that agent runs as the main
  thread (`claude --agent`); sub-agents cannot spawn sub-agents.

The picker roster is `kit-orchestrator`, `kit-debug` and `kit-devops` (only with
the iac bundle). Specialist advisers (`kit-ddd`, `kit-sdd`, `kit-deep-thinking`),
`kit-refactor` and all other helpers are hidden workers that coordinators can
call. Every role
has offline shell access to inspect history, diffs and checks. Source-read-only intent is not a
read-only shell sandbox: verifiers can still write files or use the network, and
host permissions and approvals remain necessary. See the canonical
[native-role contract](../packages/shared/.apm/skills/kit-agent-runtime/references/native-roles.md).

There is no documented workspace setting to hide arbitrary built-in and
extension-contributed agents while retaining custom agents. `chat.agent.enabled`
disables agent functionality, not just unwanted picker entries; organization
agent discovery settings do not hide built-ins or extension agents. No speculative
hide setting or user-global extension mutation is installed here.

Use **Configure Custom Agents** in the picker to identify an entry's source
(hover for its location), and **Chat > Diagnostics** to inspect discovery errors.
For a custom agent you own, `user-invocable: false` is the supported picker-hide
control, and changes the shared definition for everyone. As of the public docs
checked on 2026-11-02, the Customizations editor has no custom-agent eye-icon
show/hide control in Local or Copilot; do not rely on older picker instructions.
For an extension-contributed agent, the documented fallback is to manage its
contributing extension. An operator can choose **Disable (Workspace)** where
offered, affecting all that extension's features; this kit does not do so.
Built-in entries can remain, so a kit-only picker cannot be promised.

After source changes, audit drift with `python -m scripts.render_native` before
an explicit `--write`. Reload the selected harness and verify discovery and a
bounded worker call after generation; file tests alone do not certify runtime
behavior.

Do not add unreviewed plugin rosters, legacy `chat.mcp.autoStart`, duplicate
Claude hook locations or trust/approval shortcuts. The configured servers and
their limits are recorded in [MCP adoption](mcp-adoption.md). VS Code MCP
auto-start remains `never`; host trust, OAuth and tool consent remain separate.

## Verification and limits

The native contract checks pin interpreter, formatter/type-checker ownership,
pytest discovery and agent safeguards. Workspace regressions check source
visibility, extension providers, manual Task wrappers and debug inputs. The
existing task-wiring checks compare every target with the actual Taskfile.

The setting identifiers were checked against VS Code 1.141.0, Ruff extension
2026.88.0 and ty extension 2026.80.0, plus the official references below.
Terminal activation is not forced: the Python Environments extension's
`python-envs.terminal.autoActivationType` is machine-scoped, not portable
workspace policy.

JSON/schema checks and interpreter selection do not certify save actions,
debugger interaction, hosted agent permissions or all installed extensions.
In a fresh profile, open Python/YAML/TOML/Markdown files, run the named tasks
and debug entry points, and inspect **Chat: Open Customizations** for the chosen
harness. Multi-root users must place window-scoped settings in the workspace
file rather than assuming folder settings override them.

## Primary sources

- [VS Code custom-agent discovery and picker controls](https://code.visualstudio.com/docs/copilot/customization/custom-agents)
- [VS Code subagent invocation and allowlists](https://code.visualstudio.com/docs/copilot/agents/subagents)
- [VS Code AI settings](https://code.visualstudio.com/docs/agents/reference/ai-settings)
- [VS Code agent-folder scan implementation](https://github.com/microsoft/vscode/blob/main/src/vs/workbench/contrib/chat/common/promptSyntax/utils/promptFilesLocator.ts#L660-L695)
- [VS Code settings and scopes](https://code.visualstudio.com/docs/configure/settings)
- [Python interpreter and testing settings](https://code.visualstudio.com/docs/python/settings-reference)
- [Python debugging](https://code.visualstudio.com/docs/python/debugging)
- [Ruff editor configuration](https://docs.astral.sh/ruff/editors/settings/)
- [ty editor integration](https://docs.astral.sh/ty/editors/)
- [ty editor settings](https://docs.astral.sh/ty/reference/editor-settings/)
- [VS Code MCP servers](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [Agent skills and harness discovery](https://code.visualstudio.com/docs/agent-customization/agent-skills)
- [Custom instruction formats](https://code.visualstudio.com/docs/agent-customization/custom-instructions)
