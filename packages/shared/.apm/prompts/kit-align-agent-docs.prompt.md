---
description: Prune agent docs (AGENTS.md, instructions, skills, prompts, roles) to guardrails, exact commands and conventions the agent cannot infer.
argument-hint: Agent file or folder to review, or empty for all agent context
agent: agent
---

# Align agent documentation

Context files cost tokens on every request. Keep what changes behavior; cut
what the agent can read from the code.

## Input

- The user-supplied argument names a file or folder. When it is empty, review
  `AGENTS.md`, `CLAUDE.md`, instruction files, skills, prompts, and agent roles.

## Procedure

1. Load [kit-context-engineering](../skills/kit-context-engineering/SKILL.md)
   and [kit-agent-runtime](../skills/kit-agent-runtime/SKILL.md).
2. Measure first: run the context budget checker and record characters per
   always-on file and per skill description.
3. For each statement, keep it only if it is a guardrail, an exact command, a
   convention a linter cannot enforce, or a pointer to the owning doc.
   Delete repository overviews, restated code, and duplicated rules.
4. Instructions: a few always-true bullets with a narrow `applyTo`. Skills: a
   numbered procedure with detail in `references/`. Prompts: one task each.
5. Roles: few user-facing agents; specialists stay hidden workers with least
   privilege, and every role can read files and run offline checks.
6. Verify every command and path still works. Re-run the budget checker.

## Acceptance gates

- [ ] Always-on context is smaller or unchanged, never larger without reason.
- [ ] Every command and link in agent files resolves and runs.
- [ ] No rule is stated in two places.

## Output

Characters before and after per file, statements removed or moved with
reasons, and the checks run with results.
