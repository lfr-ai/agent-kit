# Runner choice, stages and budgets

Local hooks are a fast-feedback layer. Choose one runner, assign each check to
the cheapest stage that still catches it, and keep every stage inside a time
budget the team accepts.

## pre-commit or lefthook

| Question | pre-commit | lefthook |
| --- | --- | --- |
| What does it run | hook repositories pinned by `rev`, plus `repo: local` commands | commands and scripts defined in the repository, plus optional remote configs |
| Runtime | Python tool; creates isolated environments per hook language | single binary, no per-language environments |
| Sharing hooks across projects | strong: hook repositories are versioned and reusable | possible through remote configuration; mostly project commands |
| Parallel execution | hooks run in order; each hook spreads file batches across processes | `parallel: true` per hook |
| File selection | `files`, `exclude`, `types`, `types_or` per hook | `glob`, `files`, `exclude` per command |
| Supply-chain pinning | `rev` frozen to a commit SHA; `autoupdate --freeze` | pin the binary version in the install step; review remote config refs |
| Local overrides | none by design; use environment variables for a skip | a `lefthook-local` file merged over the main config |
| Pick it when | the repository mixes languages and wants community hooks | the hooks are mostly the project's own commands and speed matters |

Decision rules:

1. Keep the runner already in the repository. Migrating runners costs more than
   the difference between them.
2. A repository already managing Python tools with a lockfile gets the most
   from pre-commit local hooks that call `uv run --locked`; a JavaScript
   repository with a locked package manager can do the same with its runner.
3. Never run two runners that write to `.git/hooks`. Installing one over the
   other silently replaces hooks.
4. A custom `core.hooksPath` redirects Git away from `.git/hooks`. pre-commit
   refuses to install while it is set; decide whether the path or the runner
   wins and record it.

## Stage assignment

| Stage | Purpose | Put here | Budget guidance |
| --- | --- | --- | --- |
| `pre-commit` | staged-file feedback | whitespace and end-of-file fixers, syntax checks (YAML, TOML, JSON), formatter and linter checks, secret scan of staged files, spelling of changed prose | seconds; if a developer notices it every commit, it is too slow |
| `commit-msg` | message rules | Conventional Commits validation | well under a second |
| `pre-push` | whole-project feedback before sharing | type check, unit tests, lockfile consistency, import or architecture contracts | tens of seconds to a few minutes |
| `manual` | on demand | full gate, link checks, history secret scan, container or network-bound checks | no limit; also run in CI |

Rules of thumb:

- Whole-project tools use `pass_filenames: false`; file-scoped tools receive the
  staged files. Use `always_run: true` only for checks that must run even when
  no matching file changed.
- A check that needs the network or a container belongs in `manual` and CI
  unless the team accepts the latency and failure mode on every commit.
- The hook definition is the same `entry` CI runs, not a copy of its arguments.
- `fail_fast: false` (the default) reports every failure in one run, which is
  usually better than stopping at the first.
- Set `minimum_pre_commit_version` so an old installed runner fails with a clear
  message instead of ignoring newer keys.

## Check-only versus fixing hooks

| Hook type | Rewrites files | Policy |
| --- | --- | --- |
| Whitespace, end-of-file, line-ending fixers | yes | allowed: idempotent and easy to review |
| Formatters (code) | yes, unless run in check mode | run in check mode in hooks; fix with an explicit task |
| Linters with auto-fix | yes, unless run in check mode | run without `--fix` in hooks |
| Secret scanners, type checkers, tests | no | always check-only |

When a fixer hook changes files, the commit aborts so the author can review and
re-stage. Do not hide that by chaining `git add` inside a hook.

## Installation

- Provision hooks in the bootstrap step with one command; document it in the
  contributing guide. Set `default_install_hook_types` in the configuration so
  the command installs the stages you use, for example
  `[pre-commit, commit-msg, pre-push]`.
- Prewarm environments in bootstrap. Hook environments are created on first use,
  which fails offline and surprises the first commit.
- A new clone has no hooks. CI is therefore the control for anything that must
  hold; see [bypass and agent hooks](bypass-and-agent-hooks.md).

## Frozen revisions and updates

- Pin each hook repository `rev` to a full commit SHA and keep the version as a
  comment. `pre-commit autoupdate --freeze` writes that form.
- Update in a dedicated, reviewed change. Let a dependency bot propose it when
  it supports the hook configuration format, and check the diff for new hooks,
  changed `entry` commands and changed default arguments.
- Project-local hooks (`repo: local`) call tools pinned in the project lockfile,
  so the same version runs in hooks, CI and the editor.
- A pin checker in the gate rejects mutable revisions, package runner downloads
  and unlocked installs.

## Measuring the budget

1. Time each stage on a typical change by running its command under a timer,
   for example `pre-commit run --hook-stage pre-push`, or use the runner's
   verbose timing.
2. Record the result in the review record, with the machine class.
3. When a stage exceeds its budget, narrow `files`, move whole-project checks to
   `pre-push`, move network checks to `manual` and CI, and re-measure.
4. Never raise the budget to make a slow hook acceptable without recording who
   accepted it.

## Primary sources

- pre-commit, [documentation](https://pre-commit.com/)
- pre-commit, [supported hooks](https://pre-commit.com/hooks.html)
- Git, [githooks](https://git-scm.com/docs/githooks)
- Git, [git-config](https://git-scm.com/docs/git-config)
- lefthook, [configuration](https://lefthook.dev/configuration/)
- lefthook, [documentation](https://lefthook.dev/)
