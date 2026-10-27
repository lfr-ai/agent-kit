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
   install extensions or disable ones already installed.
3. Run **Tasks: Run Task > Bootstrap locked environment**, or `uv sync --locked`.
   This is an explicit install of the declared project environment, not a
   folder-open task.
4. Run **Python: Select Interpreter** and select the repository's `.venv`.
   The portable default points to the directory, so Windows and Unix do not need
   different executable paths. Changing this default does not replace a previous
   workspace interpreter selection.
5. Use **Run Build Task** for `task verify`, or **Run Test Task** for all test
   tiers. The other editor tasks cover bootstrap, types, lint, formatting,
   pre-commit, APM smoke and an interactive Conventional Commit prompt. Use `task verify -- <gate>` or the owning CLI for
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
Native Claude keeps its own adapter. Current Copilot harness discovery differs from Local and does not use
deprecated custom-location settings; this workspace does not pretend those
settings isolate a harness.

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

- [VS Code settings and scopes](https://code.visualstudio.com/docs/configure/settings)
- [Python interpreter and testing settings](https://code.visualstudio.com/docs/python/settings-reference)
- [Python debugging](https://code.visualstudio.com/docs/python/debugging)
- [Ruff editor configuration](https://docs.astral.sh/ruff/editors/settings/)
- [ty editor integration](https://docs.astral.sh/ty/editors/)
- [ty editor settings](https://docs.astral.sh/ty/reference/editor-settings/)
- [VS Code MCP servers](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [Agent skills and harness discovery](https://code.visualstudio.com/docs/agent-customization/agent-skills)
- [Custom instruction formats](https://code.visualstudio.com/docs/agent-customization/custom-instructions)
