---
description: Bootstrap a new project's repository, editor, verification and docs, then apply every installed standards prompt in a fixed order.
argument-hint: Project purpose, language, local target folder and approved scope
agent: agent
---

# Bootstrap a new project's local working setup

Combine existing setup procedures; do not introduce a scaffolding framework.

## Input

- The user-supplied argument gives the purpose, language, target and approved
  scope. Resolve missing consequential choices before making changes.
- Preserve existing files, local changes and the project's chosen tools.

## Procedure

1. Inspect the target, manifests and operating policy before writing. Use
   [kit-change-plan](../skills/kit-change-plan/SKILL.md) for a proportionate
   plan and acceptance checks; obtain approval for unapproved scope.
2. Follow [kit-repository-setup](../skills/kit-repository-setup/SKILL.md) for
   missing repository hygiene and community files. Merge only what this project
   needs; leave no adopted placeholder and preserve unrelated files.
3. Use [kit-verify-change](../skills/kit-verify-change/SKILL.md) to declare
   focused checks and the completion gate through existing tools. Resolve
   dependencies through the project's reviewed manifest and lock workflow;
   never install them without the required approval.
4. Follow [kit-editor](../skills/kit-editor/SKILL.md) to merge workspace-local
   settings, extensions and thin task wrappers. For Python, keep Ruff for
   formatting/linting/imports and ty for types; retain unwanted recommendations.
   Do not change user-global settings or install or disable extensions.
5. Follow [kit-documentation](../skills/kit-documentation/SKILL.md) for a short
   README quick start and project command reference. Link the owning policy
   instead of copying long conventions. Record only commands actually tested.
6. Run the declared local checks and task-wiring checker, and fix failures in
   scope. Report unsupported languages or unavailable tools explicitly.
   Repository initialization, commits, publication, remote settings and
   deployment remain separately approved operator actions.
7. Once code exists, run the installed standards prompts in this order, one
   reviewed change each: `/kit-align-structure`, `/kit-align-ordering`,
   `/kit-align-typing`, `/kit-align-docstrings`,
   `/kit-centralize-cross-cutting`, `/kit-align-python-conventions`,
   `/kit-align-tests`, `/kit-reduce-cognitive-load`, `/kit-align-consistency`,
   `/kit-write-docs`, then `/kit-align-agent-docs`. Skip prompts whose package
   is not installed; commit with `/kit-write-commit-message`.

## Acceptance gates

- [ ] Existing work is preserved and every adopted file has project-owned facts.
- [ ] Local editor tasks call declared checks; tools have one owner each.
- [ ] Setup commands and checks pass, or their limitations are explicit.
- [ ] No credential, user-global mutation or unapproved installation is added.

## Output

List changed paths, exact checks with results, and remaining operator actions.
Separate file validation from live editor or deployment verification.
