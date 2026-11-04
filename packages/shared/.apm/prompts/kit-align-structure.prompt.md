---
description: Align folders, subfolders, module names and layer placement with the architecture and naming conventions, updating every reference.
argument-hint: Package or folder to restructure, or empty for the whole repository
agent: agent
---

# Align structure and naming

Make the tree say what the system does and where each rule lives.

## Input

- The user-supplied argument names the package or folder. When it is empty,
  review the whole repository source tree.

## Procedure

1. Load [kit-hexagonal-architecture](../skills/kit-hexagonal-architecture/SKILL.md)
   and [kit-consistency](../skills/kit-consistency/SKILL.md). Read the
   project's architecture notes and import contracts first.
2. Map current folders to layers (domain, application, adapters, presentation,
   composition) and list misplaced modules with the import that proves it.
3. Find naming drift: mixed singular and plural folders, inconsistent suffixes,
   generic names (`utils`, `helpers`, `misc`, `common`), and folders with one
   file or more than about a dozen unrelated files.
4. Propose the target tree as a short table (old path, new path, reason).
   Group by cohesion, not by file type. Get approval before large moves.
5. Move in small steps with `git mv`; update imports, tests, config, entry
   points, docs, and import contracts in the same change.
6. Run the architecture checker, linter, type checker, and tests after each
   step.

## Acceptance gates

- [ ] Every module sits in the layer that owns it; import contracts pass.
- [ ] No generic catch-all folder or stale path remains.
- [ ] Tests pass with unchanged assertions.

## Output

The before-and-after tree for changed areas, moves with reasons, references
updated, and the commands run with results.
