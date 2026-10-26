# Choosing the artifact: instruction, skill, prompt file or agent

Reviewed: 2026-10-23.

Each artifact type loads differently, so the same text costs a different
amount of context depending on where it lives. Choose by when the guidance
must be present and who decides to load it.

## Decision table

| The guidance is ... | Use | Loaded | Example |
| --- | --- | --- | --- |
| A rule true for every task in the repository | entry file (`AGENTS.md`) line | always | "Never commit secrets" |
| A rule true for one file type or folder | scoped instruction (`applyTo`) or Claude rule (`paths`) | when matching files are touched | "Python dataclasses are frozen and slotted" |
| A multi-step procedure for a recurring task | skill | when its description matches the task | "Write a database migration" |
| A user-invoked entry point that starts one workflow with an argument | prompt file | when the user invokes it | "/plan-change issue-42" |
| A role with its own tools, permissions or model, run in its own context | agent (custom agent or subagent) | when invoked or delegated to | read-only security reviewer |
| A command, version, path or owner | project facts file | when read | test command |
| History, rationale, lessons | decision records and memory files | when read | "why the event log" |
| Something a tool can enforce | a check or test, plus a one-line pointer | at check time | lint rule |

## Tie-breakers

- If guidance has steps, it is a skill, not an instruction.
- If it only makes sense when a user starts it explicitly, it is a prompt file
  that delegates to a skill for the procedure.
- If it needs different tools or permissions, it is an agent; keep its body
  short and link the skill that owns the procedure.
- If two artifacts would say the same thing, keep the one with the narrowest
  loading and link it from the other.
- If a rule can be checked, write the check; keep at most one line of prose.

## Prompt files versus skills

| Aspect | Prompt file | Skill |
| --- | --- | --- |
| Who triggers it | the user, by name | the agent, by description match (or the user) |
| Input | a user-supplied argument | the current task |
| Content | short orchestration: inputs, steps, output format | the procedure, gates and resources |
| Portability | host-specific invocation | portable format across hosts that support skills |

A good prompt file is under about 80 lines and links the skill that owns the
procedure instead of restating it.

## Size guidance

| Artifact | Target |
| --- | --- |
| Entry file | rules and links only; measure it; Claude suggests under 200 lines per `CLAUDE.md` |
| Instruction file | a few always-true bullets, short enough to read at a glance (for example 20 lines) |
| Skill body | short numbered procedure; the specification recommends under 500 lines |
| Description | one sentence, trigger first, within the catalog budget |
| Agent body | mission, inputs, method, gates, stop condition, report outline |

## Primary sources

- [VS Code customization overview](https://code.visualstudio.com/docs/agent-customization/overview)
- [VS Code prompt files](https://code.visualstudio.com/docs/agent-customization/prompt-files)
- [VS Code custom instructions](https://code.visualstudio.com/docs/copilot/customization/custom-instructions)
- [Claude Code memory and rules](https://code.claude.com/docs/en/memory)
- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [Agent Skills specification](https://agentskills.io/specification)
