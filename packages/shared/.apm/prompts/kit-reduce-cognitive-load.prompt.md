---
description: Lower the cognitive load of code, tasks, containers and docs - shorter functions, flatter flow, fewer concepts, clear names - without behavior change.
argument-hint: Path, module, task file, or doc to simplify
agent: agent
---

# Reduce cognitive load

Make each unit understandable in one read by someone new to it.

## Input

- The user-supplied argument names the path, module, task file, Dockerfile, or
  document. When it is empty, start with the largest and most-changed files.

## Procedure

1. Load [kit-refactor](../skills/kit-refactor/SKILL.md) and its
   [complexity reference](../skills/kit-refactor/references/complexity.md).
   Run the focused tests for a green baseline.
2. Rank hot spots by size, nesting, branch count, parameter count, and change
   frequency. Pick the top few; do not sweep the whole repository at once.
3. Code: use guard clauses, extract named helpers, replace flags with separate
   functions, name magic numbers, and delete dead code and unused options.
4. Tasks and containers: one obvious entry point per workflow, no wrapper that
   only renames a tool, multi-stage images with fewer layers and pinned bases.
5. Docs: lead with the command or example, cut repetition, link the owner.
6. Apply one transformation at a time and re-run the focused tests.
7. Run the linter, type checker, and the completion gate.

## Acceptance gates

- [ ] Each changed unit is shorter or flatter, with a named reason.
- [ ] No new abstraction exists without two current uses.
- [ ] Tests pass with unchanged assertions; behavior is unchanged.

## Output

Hot spots before and after (lines, nesting, branches), transformations applied,
items left with reasons, and the commands run with results.
