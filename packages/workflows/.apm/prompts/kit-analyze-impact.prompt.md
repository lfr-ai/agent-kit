---
description: Analyze the blast radius of changing a module, symbol, or endpoint with read-only graph queries, mapping impacted callers, tests, and owners.
argument-hint: Module, symbol, or endpoint you plan to change
agent: ask
---

# Analyze change impact

Answer "what breaks if this changes?" with evidence before anyone edits. This
prompt is read-only: do not modify code, regenerate indexes, or install tools.

## Input

- The user-supplied argument names the module, symbol, endpoint, table, or
  configuration key, and ideally the kind of change (rename, signature,
  behavior, removal). Ask for the change kind if it is missing; impact differs.

## Procedure

1. Load [kit-graph-analysis](../skills/kit-graph-analysis/SKILL.md) and follow
   its procedure and tool contract.
2. State the target and the question in one sentence.
3. Pick read-only tooling the project already has; otherwise use the skill's
   import graph tool for Python packages and plain text search elsewhere.
4. Build the module graph and check for cycles first; a cycle widens every
   impact set.
5. Query direct dependents at depth one, then widen transitively until the
   set stops growing or reaches a public boundary (API, CLI, event, package
   export).
6. Descend to symbols: confirm which dependents actually use the target
   symbol, not just the module.
7. Cross-check blind spots that graphs miss: string-based lookups, reflection,
   dependency injection registration, serialization keys, configuration,
   templates, migrations, test patch targets, and other repositories.
8. For each impacted module, find the tests that exercise it and the owner
   named in ownership files or history.
9. Classify each impact as must-change, must-retest, or unaffected-but-near,
   with the evidence that justifies it.
10. Suggest the safest change order (for example add, migrate callers, remove)
    when the target has external consumers.

## Acceptance gates

- [ ] Every impacted item cites the query or file that proves it.
- [ ] Blind-spot checks were run and their results stated.
- [ ] Public boundaries crossed are named explicitly.
- [ ] No file was modified.

## Output

An impact table (item, relation, classification, tests, owner, evidence), a
list of public boundaries reached, blind-spot results, the recommended change
order, and the commands used so the analysis can be repeated.
