# Recommended extensions and keybinding chords

## Workspace extension recommendations

`.vscode/extensions.json` (or the `extensions` block of a `.code-workspace`
file) lists extensions a contributor is prompted to install when they open the
repository, and extensions they are advised not to use there.

- `recommendations`: identifiers in `publisher.name` form. Recommend only
  what the repository's own tooling relies on: the language extension, the
  formatter/linter that matches the committed tool configuration, the task
  runner integration, and file-format support for files the repository owns.
- `unwantedRecommendations`: extensions that would fight the repository's
  tools, typically a second formatter or linter for the same language. VS Code
  does not uninstall or disable them; it only stops recommending them and shows
  them as not recommended for this workspace.

The [extensions template](../assets/extensions.json.template) recommends
EditorConfig, the Task integration, YAML, Markdown lint, a spell checker, the
Python language and debugger extensions and Ruff, and marks other Python
formatters and linters as unwanted. Remove the Python entries in a repository
without Python, and swap Ruff for the formatter the repository actually
configures.

Review each identifier before committing it:

1. Confirm the publisher and identifier in the Marketplace or the Open VSX
   registry the team uses; look-alike names exist.
2. Read the extension's requested capabilities, telemetry statement and
   license. A recommendation is an endorsement that contributors will follow.
3. Prefer extensions that read the repository's tool configuration (for
   example the formatter's own config file) over extensions with their own
   settings, so CI and the editor share one source of truth.
4. Do not recommend extensions that require an account, a paid license or a
   network service unless the repository documents that dependency.
5. Keep the list short; every entry is a prompt for every new contributor.

Extension settings that change output (for example which formatter handles a
language) go in the workspace settings inside a language block; see
[workspace settings](workspace-settings.md).

## Keybindings

Keybindings are **user-scoped**: they live in the user profile's
`keybindings.json` and cannot be committed as a workspace file. The
[keybindings template](../assets/keybindings.json.template) is therefore a
personal starting point, shared as documentation rather than configuration.

### Chords

A chord is two key presses separated by a space in the `key` value:
`"ctrl+k ctrl+alt+v"` means press Ctrl+K, release, then press Ctrl+Alt+V.
VS Code reserves `ctrl+k` (`cmd+k` on macOS) as its own chord prefix for many
built-in commands, so a second press with an extra modifier rarely collides.
The template uses this layout:

| Chord | Command | Notes |
| --- | --- | --- |
| `ctrl+k ctrl+alt+v` | run the `Verify` task | disabled while debugging |
| `ctrl+k ctrl+alt+t` | run the `Test` task | disabled while debugging |
| `ctrl+k ctrl+alt+l` | run the `Lint` task | |
| `ctrl+k ctrl+alt+r` | re-run the last task | |
| `ctrl+k ctrl+alt+x` | terminate a running task | |
| `ctrl+k ctrl+alt+d` | pick and start a debug configuration | |
| `ctrl+k ctrl+alt+p` | type `task --list` into the focused terminal | only when the terminal has focus |

`workbench.action.tasks.runTask` takes the task **label** as `args`. The label
must match exactly, so keep labels stable once keybindings refer to them.

### Rules for adding a binding

1. Open **Preferences: Open Keyboard Shortcuts**, search for the proposed key,
   and check the "Record Keys" result for conflicts before adding it.
2. Add a `when` clause that limits the binding to where it makes sense
   (`terminalFocus`, `editorTextFocus`, `!inDebugMode`, `resourceLangId ==
   python`). A binding without `when` is active everywhere.
3. On macOS replace `ctrl` with `cmd` where the platform convention expects it;
   `keybindings.json` has no per-platform keys, so keep a copy per machine or
   rely on Settings Sync, which syncs keybindings per platform by default.
4. To remove a default binding, add the same key and command prefixed with `-`
   (for example `"command": "-workbench.action.tasks.build"`) instead of
   rebinding over it.
5. Use **Developer: Toggle Keyboard Shortcuts Troubleshooting** to see which
   rule handled a key press when a binding does not fire.

### Agents and keybindings

An agent cannot press keys; a keybinding is for the person working alongside
it. Point agents at the Taskfile targets directly, and document the matching
editor labels so both run the same gate.

## Sources

- [Extension recommendations](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace#_workspace-recommended-extensions)
- [Key bindings](https://code.visualstudio.com/docs/configure/keybindings)
- [When clause contexts](https://code.visualstudio.com/api/references/when-clause-contexts)
- [Settings Sync](https://code.visualstudio.com/docs/configure/settings-sync)
