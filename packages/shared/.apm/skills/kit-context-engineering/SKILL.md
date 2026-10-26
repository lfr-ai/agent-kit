---
name: kit-context-engineering
description: Use when trimming always-on agent context, writing discovery descriptions, or choosing instruction, skill, prompt or agent.
license: MIT
---

# Engineer context for agent configuration

## Procedure

1. Inventory what loads by default on each target host: entry files
   (`AGENTS.md`, `CLAUDE.md` and its imports, the Copilot instructions file),
   instructions scoped to every file, unscoped Claude rules, and all skill
   and agent descriptions. Loading rules per host are in
   [context principles](references/principles.md#what-loads-when).
2. Measure, do not guess: run
   [`check_context_budget.py`](assets/check_context_budget.py)
   (`python check_context_budget.py --root . --max-file-chars 8000 --max-total-chars 16000`)
   and record the numbers in the
   [context budget worksheet](assets/context-budget.md.template). Characters
   are the stable unit; token counts vary by model.
3. Place each piece of guidance with the
   [artifact decision table](references/artifact-choice.md): always-true
   rules in instructions, procedures in skills, one-off task entry points in
   prompt files, isolated roles in agents, facts in project files.
4. Move detail out of always-on files: keep entry files to rules true for
   every task plus links; scope instructions with the narrowest `applyTo` or
   `paths` glob; push examples and tables into skill references loaded on
   demand.
5. Write descriptions for discovery: start with the trigger ("Use when ..."),
   use the words a requester types, name what distinguishes the item from its
   neighbors, and stay within the length budget. See
   [description writing](references/principles.md#descriptions-drive-discovery).
6. Remove duplication across hosts: one portable source, thin host adapters
   that import or link it. Contradictory copies cost context and adherence.
7. Minimize exposed tools and servers per role, isolate broad research in a
   subagent that returns a summary, and keep stable content first so prompt
   caching can reuse it, as described in
   [tools, isolation and caching](references/principles.md#tools-isolation-and-caching).
8. Choose a model tier by task (exploration, implementation, review) using
   names the host currently offers; do not pin a model that may be
   unavailable. Model selection belongs in host configuration, not in
   portable text.
9. Re-run the checker and compare with the baseline in the worksheet; report
   the before and after character counts, never estimated token savings.

## Acceptance gates

- Every always-on file has a measured character count within the agreed
  limits, or an approved, recorded exception.
- No procedure, example block or project history lives in an always-on file.
- Each instruction has the narrowest scope that matches its files; at most
  one short instruction applies to every file.
- Each description starts with its trigger and differs from its neighbors.
- No rule is duplicated across hosts; adapters import or link the source.
- Claims about savings cite measured characters; nothing claims token,
  latency or cost results that were not measured on a host.
