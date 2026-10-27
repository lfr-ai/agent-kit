---
name: kit-editor
description: Use when configuring repository-scoped editor assistance or reviewing optional MCP integrations and their native setup.
license: MIT
---

# Keep editor configuration thin, shared and advisory

## Procedure

1. Inventory what exists: `.vscode/` files, any `.code-workspace` file,
   `Taskfile.yml`, tool configuration files, and native agent configuration.
   Record which editors the repository supports; do not add files for others.
2. Decide the scope of each setting with
   [workspace settings](references/workspace-settings.md): commit only settings
   that change output or file visibility; personal preferences stay in user
   settings. Merge the [settings template](assets/settings.json.template) key
   by key, never overwrite an existing file.
3. Wire editor tasks as thin wrappers around Taskfile targets following
   [tasks and launch](references/tasks-and-launch.md). Start from the
   [workspace tasks template](assets/tasks.json.template); keep personal
   cross-repository shortcuts in [user tasks](assets/user-tasks.json.template).
   Without a Taskfile, use the Taskfile template from `kit-verify-change`.
4. Run the [task wiring checker](assets/check_task_wiring.py) with `--tasks`
   and `--taskfile`; fix every finding before continuing.
5. Add debug entry points from the [launch template](assets/launch.json.template)
   only for languages the repository uses, using the same entry points and
   arguments as the matching Taskfile target and `preLaunchTask` for setup.
6. Recommend the extensions that match the repository's tools and mark
   competing formatters/linters unwanted, per
   [extensions and keybindings](references/extensions-and-keybindings.md),
   starting from the [extensions template](assets/extensions.json.template).
7. Document optional personal chords from the
   [keybindings template](assets/keybindings.json.template); keybindings are
   user-scoped and are never committed as workspace configuration.
8. For multi-root workspaces, put resource settings in each folder's
   `.vscode/settings.json`, window settings in the `.code-workspace` file, and
   target folders with `${workspaceFolder:Name}`.
9. Keep portable agent guidance in the repository's owned instruction sources;
   editor-specific metadata stays in its native adapter and links to them.
10. For optional MCP integrations follow the
    [integration adoption gates](references/mcp.md), choose one reviewed server
    from the [VS Code](assets/mcp-vscode.json.template) or
    [Claude](assets/mcp-claude.json.template) resource, and retain an
    [integration decision](assets/integration.md.template). The
    [integration catalog](assets/integration-catalog.json) has no default
    active server; never install the example roster wholesale.
11. Preserve unrelated workspace settings and never rewrite user or global
    editor configuration on someone else's behalf.
12. State which files changed, which checks ran, and which behavior still
    needs a live editor session.

## Acceptance gates

- Every committed setting is justified by shared output, visibility or tooling;
  no absolute path, credential, machine-scoped key or personal preference.
- The wiring checker exits 0, and each editor task is `process` (or `shell`)
  calling `task` with one declared target and `cwd` set to the workspace folder.
- Default build and test groups are each assigned to at most one task.
- Launch configurations reference no secrets, bind attach ports to loopback,
  and mirror a Taskfile target.
- Recommended and unwanted extensions agree with the committed formatter and
  linter configuration.
- APM package composition does not activate MCP servers; consumer-owned native
  configurations require a filled decision record.
- File checks are not reported as a tested editor session; a live check (open
  the folder in a fresh profile and run each task) is listed as done or pending.
