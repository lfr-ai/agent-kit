# Tasks as thin Taskfile wrappers, and launch configurations

The repository's task runner (here: [Task](https://taskfile.dev/) and its
`Taskfile.yml`) is the single source of truth for how to build, test, lint and
verify. Editor tasks only give those targets a button and a keybinding. When an
editor task embeds its own command line, CI and the editor drift apart and the
editor silently runs a different gate.

## The wrapper contract

Every committed editor task that runs repository tooling should:

1. Use `"type": "process"` and `"command": "task"` so no shell interprets the
   arguments. Use `"shell"` only when the command genuinely needs shell syntax,
   and then still call `task`.
2. Pass exactly the Taskfile target as an argument, for example
   `"args": ["verify"]`. Put flags and pass-through arguments in the Taskfile
   target, not in the editor task.
3. Set `"options": {"cwd": "${workspaceFolder}"}` so the task runs where the
   Taskfile lives, even when the active file is deep in the tree.
4. Set `"problemMatcher": []` unless a matcher is known to parse the tool's
   output; a wrong matcher creates false problems, and omitting the property
   makes VS Code prompt every run.
5. Use `group` only for the one default build task and the one default test
   task, so **Run Build Task** and **Run Test Task** are unambiguous.

The [workspace tasks template](../assets/tasks.json.template) follows this
contract for `verify`, `test`, `lint` and `format`. Rename or remove entries so
each label names a target the consumer's Taskfile declares.

```json
{
  "label": "Verify",
  "type": "process",
  "command": "task",
  "args": ["verify"],
  "options": {"cwd": "${workspaceFolder}"},
  "problemMatcher": [],
  "group": {"kind": "build", "isDefault": true}
}
```

### Check the wiring

The [task wiring checker](../assets/check_task_wiring.py) reads
`.vscode/tasks.json` (comments and trailing commas allowed) and `Taskfile.yml`
without third-party libraries and reports every runner target that the
Taskfile does not declare:

```text
python check_task_wiring.py --tasks .vscode/tasks.json --taskfile Taskfile.yml
.vscode/tasks.json:14: task 'Deploy' targets 'deploy', which the Taskfile does not declare
```

Behavior worth knowing:

- Only tasks of type `process` or `shell` whose command is the `task`
  executable are checked; `npm`, extension-provided and other tasks are ignored.
  Platform overrides (`windows`, `linux`, `osx`) are checked too.
- Flags are skipped, including the values of `--dir`, `--taskfile` and similar
  options. `NAME=value` variables and everything after `--` are not targets.
- A call without a target requires a `default` task, unless a listing flag such
  as `--list` is present.
- Targets in an included namespace (`docs:build` with `includes: docs:`) are
  accepted because the included file is not read; pass `--verify-includes` to
  fail them instead.
- Arguments built from editor variables such as `${input:target}` cannot be
  verified and are reported; pass `--allow-dynamic` to accept them.
- The Taskfile reader understands block-style top-level `tasks:` and
  `includes:` keys only. Flow-style top-level mappings are not read.
- Exit status is 0 when clean, 1 on findings and 2 when an input cannot be read.

Run `--self-test` once after copying the checker, then wire it into the
consumer's existing check runner (a Taskfile target or a pre-commit hook). It
proves wiring, not that the targets succeed.

Its output uses `path:line: message`, so a matcher can surface findings in the
Problems panel when it runs as an editor task:

```json
"problemMatcher": {
  "owner": "task-wiring",
  "fileLocation": ["relative", "${workspaceFolder}"],
  "pattern": {"regexp": "^(.*):(\\d+):\\s+(.*)$", "file": 1, "line": 2, "message": 3}
}
```

## User-level tasks

**Tasks: Open User Tasks** creates a personal `tasks.json` that appears in
every workspace. The [user tasks template](../assets/user-tasks.json.template)
offers `Task: list targets`, `Task: verify` and `Task: test` for repositories
that follow the same convention. User tasks must never assume a target exists:
keep them to conventional names and expect them to fail cleanly in a
repository without a Taskfile. They are personal and are not committed.

## Compound tasks and dependencies

Prefer a Taskfile target with `deps` or `cmds: [task: other]` over editor
`dependsOn`, so the composition also exists in CI. Use `dependsOn` only for
editor-only orchestration such as starting a watcher before a debug session,
and set `"dependsOrder": "sequence"` when order matters.

Background tasks (watchers, local servers) need `"isBackground": true` and a
problem matcher with a `background` pattern whose `beginsPattern` and
`endsPattern` match the tool's own output; otherwise a `preLaunchTask` waits
forever.

## Launch configurations

`launch.json` describes how to start or attach a debugger. Unlike tasks, a
launch configuration cannot be a thin wrapper around the Taskfile because the
debugger must own the process. Keep it close to the Taskfile instead:

- Use the same module or entry point and the same arguments as the matching
  Taskfile target. If the target needs setup (generated code, a local
  database), call that setup through `"preLaunchTask"` naming an editor task
  that wraps the Taskfile target.
- Use `${workspaceFolder}` for `cwd`; never commit absolute paths or
  interpreter paths.
- Keep secrets out of `env`. Use `envFile` pointing to an ignored local file
  that each developer creates from a committed example without values.
- Attach configurations should bind to `127.0.0.1`, not all interfaces, and
  the debug server must be started only in local development.
- Name configurations by intent ("Python: pytest current file"), not by tool
  flags, and order them by frequency of use.

The [launch template](../assets/launch.json.template) contains debugpy
configurations for the current file, a package module, pytest on the current
file and attaching to a local debug server, plus a Node.js current-file
configuration. Replace `REPLACE_WITH_PACKAGE`, delete languages the repository
does not use and keep `justMyCode` false only where stepping into dependencies
is the point.

### Inputs and variables

`${input:id}` prompts the user through an `inputs` entry (`promptString`,
`pickString` or `command`). Inputs are convenient for launch arguments but make
tasks unverifiable; prefer one task per real target. Common predefined
variables: `${workspaceFolder}`, `${file}`, `${relativeFile}`,
`${fileDirname}`, `${env:NAME}` and `${config:setting.id}`.

## Failure and recovery

- **Task not found**: the label in a keybinding or `preLaunchTask` does not
  match a task label exactly; labels are case-sensitive.
- **`task` is not recognized**: the Task CLI is not on the `PATH` seen by the
  editor. Install it through the repository's bootstrap, then restart the
  editor so it inherits the new `PATH`.
- **Runs in the wrong folder**: `options.cwd` is missing, or a multi-root
  workspace resolves `${workspaceFolder}` to another folder; use
  `${workspaceFolder:Name}`.
- **Problems panel fills with noise**: remove a guessed `problemMatcher` and
  use `[]` until a matcher is tested against real output.
- **Debugger starts before the build finishes**: the `preLaunchTask` is a
  background task without `endsPattern`, or the build is not a dependency.

## Sources

- [Tasks](https://code.visualstudio.com/docs/debugtest/tasks)
- [Tasks appendix (schema)](https://code.visualstudio.com/docs/reference/tasks-appendix)
- [Variables reference](https://code.visualstudio.com/docs/reference/variables-reference)
- [Debugging configuration](https://code.visualstudio.com/docs/debugtest/debugging-configuration)
- [Python debugging](https://code.visualstudio.com/docs/python/debugging)
- [Task usage](https://taskfile.dev/docs/guide)
