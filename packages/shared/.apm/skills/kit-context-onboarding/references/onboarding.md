# Onboard to a new codebase in about 30 minutes

The goal is not to understand everything. It is to be able to make one safe,
verified change: know how to build and test, where the requested behavior
lives, what must not be touched, and who owns what. Stay read-only throughout.

## Minutes 0-5: identity and rules

- Read the root entry files: operating policy (`AGENTS.md` or equivalent),
  project facts, `README.md`, `llms.txt` if present.
- Read the package manifest and lockfile names to learn language, runtime
  version and package manager.
- Note approval boundaries: what you may not do without an operator.

Output: one line each for language/runtime, package manager, task runner,
completion command.

## Minutes 5-10: toolchain and gate

- Open the task runner file (Taskfile, Makefile, `package.json` scripts,
  `justfile`) and CI workflow. Find the commands CI actually runs.
- Run the install command with the lockfile, then the fastest test command.
  If either fails, stop and record the error; do not improvise fixes.

Output: exact commands that worked, with working directory and duration.

## Minutes 10-18: map the structure

- List top-level directories and identify entry points (CLI main, HTTP app,
  workers, scheduled jobs), the domain or core package, adapters, tests, and
  generated or vendored code.
- Look for an architecture document or decision records; skim headings only.
- Identify dependency direction from imports at the top of a few core files.

Output: a five-to-ten line map: directory, role, generated or authored.

## Minutes 18-25: trace one path

- Pick the public input closest to the requested change (a route, a command, a
  message type).
- Follow it from the entry point through validation, the use case, and the
  adapter that performs the side effect or returns the result.
- Find the nearest existing test for that path and run only that test.

Output: the call path as a list of `file:function` steps and the test that
covers it.

## Minutes 25-30: boundaries and gaps

- Note generated files and their generators, ownership markers (CODEOWNERS),
  and configuration that differs per environment.
- List what you could not verify: missing tools, unavailable services,
  credentials you do not have.
- Write the hand-off or plan: facts with evidence, assumptions marked as such,
  the smallest next check.

## Shortcuts that save time

| Question | Fast way to answer |
| --- | --- |
| Where is X implemented? | search for a user-visible string, route or error message, then follow references |
| What calls this? | the editor's "find all references", then a text search for dynamic uses |
| What changed recently here? | `git log --oneline -n 20 -- <path>` |
| Who knows this area? | CODEOWNERS, then `git shortlog -sn -- <path>` |
| Is this file generated? | header comments, the build configuration, `.gitattributes` `linguist-generated` |
| What does CI really run? | the workflow files, not the README |

## Output template

```markdown
## Context map (YYYY-MM-DD)

- Toolchain: <language/runtime>, <package manager>, <task runner>
- Install: `<command>` (cwd: <dir>) - result
- Focused test: `<command>` - result
- Completion gate: `<command>` - not run / result
- Path for <behavior>: entry -> validation -> use case -> adapter
- Nearest test: <file::test>
- Generated/vendored: <paths> (owner: <generator>)
- Unverified: <items and why>
```

Record durable discoveries (a surprising command, a non-obvious boundary) as
lessons with the `kit-project-memory` skill; keep the rest in the task hand-off.

## Stop conditions

- Install or tests fail in a fresh clone: report it before changing anything.
- Ownership or the effect of a change cannot be determined locally: ask.
- The requested change touches generated output: find and change the source.

## Sources

- [GitHub: about code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
- [git-log](https://git-scm.com/docs/git-log)
- [git-shortlog](https://git-scm.com/docs/git-shortlog)
- [GitHub Linguist overrides](https://github.com/github-linguist/linguist/blob/main/docs/overrides.md)
