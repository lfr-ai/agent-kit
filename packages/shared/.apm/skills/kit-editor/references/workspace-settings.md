# Workspace, folder and user settings

VS Code merges settings from several scopes. Commit only what every
contributor needs to build, test and read the repository the same way; keep
personal taste in user settings.

## Scope and precedence

From lowest to highest precedence:

| Scope | File | Owner | Commit it? |
| --- | --- | --- | --- |
| Default | built in | VS Code and extensions | no |
| User | `settings.json` in the user profile | the developer | no |
| Remote / profile | per remote host or named profile | the developer | no |
| Workspace | `.vscode/settings.json` or the `settings` block of a `.code-workspace` file | the repository | yes, when shared |
| Workspace folder | `<folder>/.vscode/settings.json` inside a multi-root workspace | the folder's owner | yes |
| Language-specific | `"[python]": { ... }` blocks at any scope | as above | as above |
| Policy | set by an administrator | the organization | no |

Every language-specific scope (user, remote, workspace, folder) overrides every
plain scope for files of that language, so a personal `"[python]"` block in
user settings beats a plain workspace `editor.formatOnSave`. Put shared
formatter choices inside a language block in the workspace file. Policy values
always win. Primitive and array values are replaced by the higher scope; object
values such as `files.exclude` are merged key by key. Check the effective value
with **Preferences: Open Settings (UI)**, which marks where a value was
modified, rather than reasoning about merge order by hand.

Some settings are machine- or application-scoped (for example terminal shell
paths, proxy settings, update channels and most telemetry settings). VS Code
ignores them in workspace files. Do not commit them and do not rely on them
from a repository.

## What belongs in the workspace file

Commit settings that change **what the tools produce** or **which files they
see**, so every contributor and agent gets the same result:

- Formatter selection and format-on-save per language, matching the
  repository's formatter configuration file (the tool's own config remains the
  source of truth; the editor only points to it).
- `files.exclude`, `search.exclude` and `files.watcherExclude` for virtual
  environments, dependency folders, build output and caches.
- `files.eol`, `files.insertFinalNewline`, `files.trimTrailingWhitespace` and
  `files.encoding` when the repository has a line-ending or encoding rule.
- Test discovery settings (for example the Python test framework and its
  arguments) that mirror the declared test runner.
- Agent features that read repository instruction files, kept consistent with
  the repository's chosen entry files.

Keep out of the workspace file:

- Themes, fonts, zoom, minimap, cursor style and other personal preferences.
- Interpreter or SDK absolute paths; use a relative virtual-environment path
  only when the repository's bootstrap command always creates it there.
- Credentials, tokens, endpoints that identify a person, and proxy settings.
- Settings for extensions the repository does not recommend.

The starting point is the [settings template](../assets/settings.json.template).
Merge it into an existing file key by key; never overwrite a contributor's
workspace file wholesale.

## JSON with comments

`settings.json`, `tasks.json`, `launch.json`, `keybindings.json` and
`extensions.json` are parsed as JSON with comments and trailing commas. Other
tools that read the same files (linters, scripts, the
[task wiring checker](../assets/check_task_wiring.py)) may be stricter.
Prefer strict JSON in committed files unless a comment explains a non-obvious
choice, and keep the templates in this skill strict so any parser can read them.

## Multi-root workspaces

A `.code-workspace` file lists several folders and can carry `settings`,
`launch`, `tasks` and `extensions` blocks of its own:

```json
{
  "folders": [
    {"path": "services/orders"},
    {"path": "services/invoices"},
    {"path": "docs", "name": "Documentation"}
  ],
  "settings": {"files.insertFinalNewline": true},
  "extensions": {"recommendations": ["editorconfig.editorconfig"]}
}
```

Rules that avoid surprises:

1. Resource-scoped settings (formatter, exclusions, language blocks) belong in
   each folder's `.vscode/settings.json`; window-scoped settings belong in the
   `.code-workspace` file. VS Code ignores window-scoped settings in folder files.
2. `${workspaceFolder}` in a folder's `tasks.json` resolves to that folder.
   In the `.code-workspace` file use `${workspaceFolder:Name}` to target one
   folder explicitly.
3. Each folder keeps its own Taskfile and its own tasks file; do not route one
   folder's tasks through another folder's paths.
4. Commit the `.code-workspace` file only when the folder layout is stable and
   shared. Otherwise document the folder list and let contributors create their
   own workspace file.
5. Workspace trust is per folder set. Restricted mode disables tasks, debugging
   and many extensions; do not instruct contributors to trust a repository they
   have not reviewed.

## Profiles and settings sync

Profiles and Settings Sync move **user** state between machines. They never
replace committed workspace settings, and a repository must work for a
contributor whose profile has none of your personal settings. Test a new
workspace setting in a fresh profile (**Profiles: New Profile**, empty) before
calling it complete.

## Review checklist

- Every committed key changes output, visibility or shared tooling; nothing is
  cosmetic.
- No machine-scoped key, absolute path, credential or personal identifier.
- Exclusions cover dependency folders, virtual environments and build output.
- Formatter and linter choices match the recommended extensions and the
  repository's tool configuration.
- In a multi-root workspace, resource settings live in folder files and
  window settings in the workspace file.
- The effective value was checked in the Settings UI for one file per language.

## Sources

- [User and workspace settings](https://code.visualstudio.com/docs/configure/settings)
- [Multi-root workspaces](https://code.visualstudio.com/docs/editing/workspaces/multi-root-workspaces)
- [Workspace trust](https://code.visualstudio.com/docs/editing/workspaces/workspace-trust)
- [Profiles](https://code.visualstudio.com/docs/configure/profiles)
- [Settings Sync](https://code.visualstudio.com/docs/configure/settings-sync)
