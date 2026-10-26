# Host differences for project memory

Every host reads plain repository files. They differ in which files they load
automatically, how they scope them, and whether they keep a private memory
store. Design for the common denominator: one portable entry file, thin host
adapters, and on-demand detail.

Reviewed: 2026-10-23. Host behavior changes often; re-check the linked
documentation before relying on a loading rule, and record what you observed
with the host name and version.

## Loading rules

| Host | Always loaded | Scoped or on demand | Private memory store |
| --- | --- | --- | --- |
| GitHub Copilot in VS Code | `.github/copilot-instructions.md`; `AGENTS.md` and `CLAUDE.md` when the harness and settings enable them | `*.instructions.md` by `applyTo` glob or by `description` relevance; skills by description; prompt files on invocation | Copilot Memory (preview) for supported Copilot surfaces |
| GitHub Copilot cloud agent and CLI | repository instructions and `AGENTS.md` per GitHub documentation | path-specific instructions, skills, custom agents | Copilot Memory (preview): repository facts with code citations, user preferences |
| Claude Code | `CLAUDE.md` files up the directory tree, user `~/.claude/CLAUDE.md`, imports with `@path`, first part of auto memory | `CLAUDE.md` in subdirectories when read; `.claude/rules` with `paths`; skills by description | auto memory per repository, written by the agent |
| Other agents reading `AGENTS.md` | `AGENTS.md`, nearest one wins in nested layouts for many tools | tool-specific | tool-specific |

## Consequences for the layout

- Write portable policy once in `AGENTS.md`. Make `CLAUDE.md` an import of it
  (`@AGENTS.md`) plus nothing portable, and make the Copilot instructions file
  a short pointer. Imported files still load in full, so an import organizes
  context but does not reduce its cost.
- Host memory stores are not shared across hosts or always reviewed. Treat
  them as personal or provisional. A fact that matters to the team moves into
  a repository file with evidence, through review.
- Copilot Memory stores repository facts with citations and validates them
  against the current branch before use; that is a useful model for repository
  lessons too: keep the evidence link next to the claim.
- Claude auto memory loads only its first part into every session. Do not let
  it become the only copy of a team decision.
- Scoped instructions load when matching files are touched; use them for rules
  that apply to a file type, not for project history.

## Cost of always-on context

| Choice | Context cost | Use it for |
| --- | --- | --- |
| Line in the entry file | every request, every task | rules true for every task, links to detail |
| Scoped instruction | requests that touch matching files | rules for one file type or folder |
| Skill body | after the skill is selected | procedures |
| Reference or asset | when the procedure links to it | tables, templates, examples |
| Memory or decision file | when an agent opens it | history, rationale, evidence |

Measure the characters of every always-loaded file instead of estimating
tokens; tokenization differs by model and host. The `kit-context-engineering`
skill owns the measurement procedure.

## Failure modes

| Symptom | Likely cause | Check |
| --- | --- | --- |
| Agent on host B ignores a rule followed on host A | rule lives only in host A's adapter or private memory | move it to `AGENTS.md` or a scoped instruction both hosts load |
| Duplicate rules contradict each other | adapter copied policy instead of linking | keep one source, make the adapter import or link it |
| Private memory contradicts a decision record | memory not reviewed after supersession | delete or correct the memory entry; the record wins |
| Entry file loads but rule is not followed | rule buried in a long file or vague | shorten, make it concrete and checkable |

## Primary sources

- [Claude Code memory](https://code.claude.com/docs/en/memory)
- [VS Code custom instructions](https://code.visualstudio.com/docs/copilot/customization/custom-instructions)
- [GitHub Copilot repository instructions](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions)
- [About GitHub Copilot Memory](https://docs.github.com/en/copilot/concepts/agents/copilot-memory)
- [AGENTS.md format](https://agents.md/)
