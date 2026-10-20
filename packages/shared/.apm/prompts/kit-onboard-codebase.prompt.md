---
description: Map an unfamiliar repository or subsystem read-only, covering toolchain, gates, structure, one traced call path, owners, and open gaps.
argument-hint: Optional focus, e.g. a subsystem, feature, or question to answer
agent: ask
---

# Onboard to a codebase

Build enough grounded context to plan a change safely. Stay read-only; the map
is the deliverable.

## Input

- The user-supplied argument names the focus: a subsystem, a feature, or a
  question such as "where are invoices validated". When it is empty, map the
  repository at the level of packages and entry points.

## Procedure

1. Load [kit-context-onboarding](../skills/kit-context-onboarding/SKILL.md) and
   follow its onboarding route.
2. Read the entry files first: operating policy, project facts, contributing
   guide, package manifests, and task runner. Record the install, focused
   test, and completion commands exactly as declared.
3. Build a structure map: top-level packages, their responsibility in one
   line, and the dependency direction between them. Note generated, vendored,
   or externally owned folders that must not be edited.
4. Trace one real call path for the focus from entry point to persistence or
   output, as `file:function` steps, and name the nearest test for each step.
5. List existing helpers, contracts, and conventions a change should reuse
   (error types, logging, configuration, factories).
6. Separate observed facts (with file evidence) from assumptions. List tools or
   services you could not reach.
7. When the agent runtime supports it, run the read-only context checker from
   the skill; report its findings without fixing them.

## Acceptance gates

- [ ] Every statement about the code cites a file you read.
- [ ] The traced path is concrete, not a generic architecture description.
- [ ] Commands are quoted from project files, not guessed.
- [ ] No files were modified.

## Output

Sections: Commands, Structure map (table), Traced path (numbered
`file:function` steps with tests), Reusable building blocks, Do-not-edit areas,
Facts vs assumptions, and Open questions. Keep it under two screens.
