# Entry files: AGENTS.md, PROJECT.md and llms.txt

Agents and new contributors read a repository through a few entry files. Each
file has one job. When two files do the same job they drift, and the agent
follows whichever it happened to read last.

## Roles

| File | Job | Changes when | Size |
| --- | --- | --- | --- |
| `AGENTS.md` | Operating policy: invariants, approval boundaries, working method, verification and hand-off rules | the team changes how work is done | short; well under a few hundred lines |
| `PROJECT.md` | Project facts: identity, supported toolchain, exact commands with working directory, layout, boundaries | the toolchain, layout or commands change | short tables and lists |
| `llms.txt` | Index for language models: a title, a one-paragraph summary and links to the files worth reading | files are added, moved or retired | a page of links |
| Knowledge index | Architecture, decisions, operations, recovery, linked to owning code | a decision is made or superseded | one row per topic |
| Native adapters (`CLAUDE.md`, `.github/copilot-instructions.md`, path-scoped instruction files) | Load the shared files into one host and add host-only details | the host's format changes | a few lines that import or link the shared files |

The [policy template](../assets/AGENTS.md.template),
[project facts template](../assets/PROJECT.md.template),
[context entry template](../assets/llms.txt.template),
[package inventory template](../assets/projects.md.template) and
[knowledge index template](../assets/knowledge-index.md.template) give a
starting structure. Fill them with evidenced facts and delete placeholders.

## AGENTS.md

`AGENTS.md` is an open convention read by many coding agents. It sits at the
repository root; nested `AGENTS.md` files in subdirectories apply to that
subtree, and the closest one to the edited file usually takes precedence.

Write rules that are **always true** and **actionable**:

- Approval boundaries: which actions need an operator (publishing, deploying,
  changing global configuration, using credentials).
- Ownership: where authored sources live and what is generated.
- Working method: inspect before editing, reproduce defects first, keep
  changes local, how to report.
- Verification: the one completion command and what it covers.

Keep out: commands with versions (they belong in `PROJECT.md`), architecture
essays (knowledge base), task history (hand-off notes), and anything a linter
already enforces.

## PROJECT.md

Facts a newcomer would otherwise discover by trial and error:

- Package or service identity and supported runtime versions.
- Exact commands with working directory and side effects: install with the
  lockfile, focused test, completion gate, build, format.
- Layout: where entry points, tests, configuration and generated output live.
- Boundaries: public contracts, trust boundaries, secrets locations (names
  only), unsupported surfaces.

Every command listed must run as written in a fresh clone. When a command
changes, update `PROJECT.md` in the same change.

## llms.txt

`llms.txt` is a proposed convention: a Markdown file at the root with an H1
title, a short blockquote summary, optional prose, and H2 sections of links
with one-line descriptions. An "Optional" section marks links that can be
skipped when context is short. It indexes; it does not restate policy.

```markdown
# Orders service

> HTTP service that stores orders and issues invoices. Python 3.13, uv, Task.

## Start here

- Operating policy: AGENTS.md (approval boundaries and verification)
- Project facts: PROJECT.md (commands, layout, toolchain)

## Optional

- Architecture decisions: docs/decisions/README.md (accepted and superseded)
```

## Native adapters

Hosts differ in which file they read. Keep one shared source and make each
native file a thin adapter:

- A host that supports imports (for example `@AGENTS.md` in a Claude memory
  file) imports the shared file and adds only host-specific notes.
- A host without imports gets a short file linking to the shared files.
- Path-scoped instruction files carry a few bullets that are always true for
  their glob; procedures belong in skills.

Do not copy the policy into each adapter. Verify, in the host itself, which
files it actually loaded; repository files cannot suppress user-level or
organization-level instructions the host also loads.

## Checks

- The [context checker](../assets/check_context.py) verifies that the entry
  files exist, are not empty and that their local links resolve. Run it with
  `--root` and, when the repository uses other names, repeated `--entry`.
- Every command in `PROJECT.md` is executed once in a fresh clone before the
  file is called correct.
- Each native adapter is opened in its host and the loaded instructions are
  inspected.

## Sources

- [AGENTS.md](https://agents.md/)
- [llms.txt proposal](https://llmstxt.org/)
- [Claude Code memory](https://code.claude.com/docs/en/memory)
- [GitHub Copilot: repository custom instructions](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions)
- [VS Code: custom instructions](https://code.visualstudio.com/docs/agent-customization/custom-instructions)
