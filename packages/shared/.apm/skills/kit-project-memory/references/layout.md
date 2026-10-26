# Memory layout: what belongs where

Project memory is ordinary, reviewed files in the repository. Any agent on any
host can read a file; few can read another host's private memory store. Put
durable project knowledge in files, and keep host memory features for personal
preferences only.

Reviewed: 2026-10-23.

## Layout

```text
AGENTS.md                      entry: operating policy, links outward
CLAUDE.md                      host adapter: imports AGENTS.md, adds nothing portable
.github/copilot-instructions.md host adapter: points to AGENTS.md
PROJECT.md                     facts: commands, versions, toolchain, owners by role
llms.txt                       short map of the repository for model readers
.agents/knowledge-base/
  README.md                    index of topics, one line each
  architecture.md              components, dependency direction, trust boundaries
  glossary.md                  terms with one meaning each
  flows.md                     ordered steps of the main workflows
  decisions/NNNN-title.md      one decision record per file (MADR style)
memories/
  README.md                    what the folder holds and what it never holds
  decisions.md                 optional dated decision log when records are small
  lessons.md                   dated, evidenced lessons
plans/ or .agents/plans/
  <topic>.md                   multi-session plan with task status
HANDOFF.md (or .agents/handoff.md)  in-flight state, deleted when done
```

Folder names are conventions, not requirements. Pick one location per kind,
record it in the knowledge base README and the entry file, and keep it.

## Placement table

| Item | Home | Lifetime | Example |
| --- | --- | --- | --- |
| Always-true rule for agents | `AGENTS.md` or a scoped instruction | until the rule changes | "Core is stdlib-only" |
| Command, version, path, owner role | `PROJECT.md` | until the tool changes | "Tests: `task test`" |
| Structure as it is now | `architecture.md` | until the structure changes | layer diagram |
| Term definition | `glossary.md` | until the term changes | "bundle" |
| Workflow steps | `flows.md` | until the workflow changes | release flow |
| Decision with alternatives and consequences | decision record | permanent; superseded, never deleted | "use an event log for orders" |
| Surprising fact with evidence | lesson entry | until re-verified false or superseded | "lockfile check needs the CI uv" |
| Multi-session work and status | plan file | until the plan is done | migration plan |
| State of unfinished work | handoff file | until the next session resumes it | "step 3 of 5, failing test X" |
| Team preference without evidence | the policy, if agreed; otherwise nowhere | until changed | "prefer guard clauses" |
| Personal preference | host user memory, never the repository | personal | editor style |
| Procedure for a recurring task | a skill | until the procedure changes | release steps |

Rules that follow from the table:

- A rule that must always hold is better as a check or test than as prose.
  Prose is the fallback.
- A fact the code, configuration or a test already states is linked, not
  restated.
- Preferences become policy only when the team agrees and they are checkable.
- Plans and handoffs are temporary. Their durable residue moves into records.

## Never store

| Content | Why | Store instead |
| --- | --- | --- |
| Secrets, tokens, connection strings | leaks through history and context | the secret store name and the variable name |
| Personal data, contact details | privacy and retention obligations | a role ("release owner") |
| Chat transcripts, raw logs | noise, possible secrets, no decision value | the decision and the one log line that proves it |
| Customer or production data | confidentiality | a synthetic example |
| Speculation, guesses, "probably" | a confident stale guess misleads later agents | an open question in the plan, or nothing |
| Copies of external docs | license and drift | the URL and the review date |

## Cost of always-on context

Entry files and instructions scoped to every file load into every request on
most hosts. Each line costs context on every turn and dilutes adherence to the
other lines. Keep entry files to links and rules that are true for every task;
put detail in on-demand files the entry links to. Measure the character count
of everything that loads by default; the `kit-context-engineering` skill owns
the budget procedure and checker.

## Failure modes

| Symptom | Cause | Response |
| --- | --- | --- |
| Two files state different commands | a fact was copied | keep the `PROJECT.md` line, link to it elsewhere |
| Agents repeat a mistake fixed last week | the lesson lives only in a host memory store | record it in `memories/lessons.md` or a check |
| Entry file over a few hundred lines | procedures and history accumulated | move procedures to skills, history to records |
| Handoff from last month still present | not closed out | fold durable parts into records, delete it |
| Decision silently rewritten | no supersession rule | restore it, add a new record that supersedes it |

## Primary sources

- [AGENTS.md format](https://agents.md/)
- [Claude Code memory and CLAUDE.md](https://code.claude.com/docs/en/memory)
- [VS Code custom instructions](https://code.visualstudio.com/docs/copilot/customization/custom-instructions)
- [GitHub Copilot repository instructions](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions)
- [Anthropic: effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [llms.txt proposal](https://llmstxt.org/)
