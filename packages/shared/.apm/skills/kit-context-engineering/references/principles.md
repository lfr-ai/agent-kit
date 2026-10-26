# Context engineering principles for agent configuration

Reviewed: 2026-10-23. Host loading rules change between releases; confirm
against the linked documentation and record the host version you observed.

Context is a finite budget shared by the system prompt, configuration,
conversation, tool definitions and tool results. Every line that loads by
default is paid on every request and competes for the model's attention with
the task. The goal is the smallest set of high-signal context that lets the
agent do the task, with everything else one link away.

## What loads when

| Layer | Examples | Loaded |
| --- | --- | --- |
| Always on | `AGENTS.md`, `CLAUDE.md` and its `@` imports, `.github/copilot-instructions.md`, instructions with `applyTo: "**"`, Claude rules without `paths` | every request on the hosts that read them |
| Metadata | skill and agent `name` and `description`, prompt file descriptions | every request, for discovery |
| Scoped | instructions whose `applyTo` matches a touched file; Claude rules whose `paths` match | when matching files are read or edited |
| On demand | a skill body after selection; agent body when invoked; prompt file on invocation | when chosen |
| Resources | skill references, assets, scripts | when the body links to them and the task needs them |

Consequences:

- Imports organize a file but do not reduce cost; imported text loads with
  the importer.
- A description is always on even though its skill is not; long descriptions
  across a large catalog add up.
- Claude strips block-level HTML comments from `CLAUDE.md` before loading;
  other hosts may not. Do not rely on comments to hide cost portably.

## Progressive disclosure

Structure each capability in three levels: metadata that identifies the task,
a body with the procedure, and resources with tables, templates and checks.
The Agent Skills specification recommends a short body (under 500 lines,
roughly 5000 tokens) with detail in referenced files one level deep. Keep
entry files to rules true for every task plus links to the rest.

## Descriptions drive discovery

Agents choose skills, instructions and agents mostly from descriptions.

- Lead with the trigger: "Use when ...". State the situation, not the topic.
- Use the requester's words (the nouns and verbs they type), not internal
  jargon.
- Name what distinguishes it from neighbors, so near-misses do not trigger it.
- One sentence, within an agreed budget (for example 350 characters; the
  Agent Skills specification maximum is 1024).
- Test with should-trigger and near-miss requests; the `kit-create-skill`
  skill owns trigger evaluation.

## Instruction length and specificity

- Prefer concrete, checkable rules ("Run `task test` before handoff") over
  general advice ("test well").
- Keep each instruction file to a few always-true bullets; procedures belong
  in skills.
- Contradictions make the model pick one arbitrarily; review instruction
  sets together.
- A rule that a linter or test can enforce should be enforced there and
  removed from prose, or reduced to a pointer.

## Scoping with applyTo and paths

- Use the narrowest glob that matches the files the rule governs.
- Reserve `**` for one short safety or policy file, if any.
- Two instructions with the same scope are a merge candidate.
- Use `paths` for Claude rules and `applyTo` for Copilot instructions; do not
  invent cross-host fields.

## Duplication across hosts

Write portable policy once (`AGENTS.md` or packaged instructions). Host
adapters import or link it: `CLAUDE.md` with `@AGENTS.md`, the Copilot
instructions file with a short pointer. When a host needs a native field
(tools, model, permissions), keep it in the host's adapter, not in portable
text. A copied rule drifts, and the drifted copy still costs context.

## Tools, isolation and caching

- **Tool exposure:** each tool definition is context. Enable only the tools
  and servers a role needs; prefer existing local tools over adding a server.
- **Subagent isolation:** send broad searches or long log analysis to a
  subagent that returns a short summary; its exploration stays out of the
  coordinator's window. Delegation rules are owned by the
  `kit-subagent-delivery` skill.
- **Caching-friendly prefixes:** prompt caching reuses an identical prefix.
  Keep stable content (policy, tool definitions, long references) first and
  unchanged between requests; put volatile content (dates, task text, file
  contents) last. Do not inject timestamps or random IDs into always-on files.
- **Compaction:** at verified milestones, keep decisions, open failures and
  the next test; drop exploration transcripts.

## Measure characters, not guessed tokens

Token counting differs by model and changes between versions; a token estimate
made from a rule of thumb is not evidence. Count characters of the files
that load, compare against limits, and report before and after numbers. Use
a host's own context view (for example Claude's `/context`) when a host
measurement is needed, and record the host and version with it.

## Model selection by task tier

| Tier | Typical work | Choose |
| --- | --- | --- |
| Fast | search, classification, summarizing, mechanical edits | a small, fast model the host offers |
| Standard | implementation, tests, routine review | the host's default general model |
| Deep | architecture, difficult debugging, security review | a larger reasoning model the host offers |

Rules: choose from the models the host currently lists; leave the model
unset in portable text so the host default applies; never pin a model name
that may be unavailable to other users; set models in host configuration or
native agent files only.

## Failure modes

| Symptom | Likely cause | Response |
| --- | --- | --- |
| Agent ignores a rule | rule buried in a long always-on file | shorten the file; scope the rule; make it checkable |
| Wrong skill triggers | vague or overlapping descriptions | rewrite with trigger and distinguishing words |
| Same rule appears in three files | per-host copies | keep one source, link from adapters |
| Context fills early in a session | broad tool exposure or pasted logs | restrict tools, return summaries, compact |
| Savings claimed without numbers | token estimates | report measured characters instead |

## Primary sources

- [Anthropic: effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Agent Skills specification](https://agentskills.io/specification)
- [VS Code customization overview](https://code.visualstudio.com/docs/agent-customization/overview)
- [VS Code custom instructions](https://code.visualstudio.com/docs/copilot/customization/custom-instructions)
- [VS Code agent skills](https://code.visualstudio.com/docs/agent-customization/agent-skills)
- [Claude Code memory and rules](https://code.claude.com/docs/en/memory)
- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [Anthropic prompt caching](https://docs.claude.com/en/docs/build-with-claude/prompt-caching)
- [Anthropic: choosing a model](https://docs.claude.com/en/docs/about-claude/models/choosing-a-model)
