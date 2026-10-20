---
description: Verify the current change with focused tests, then the declared completion gate, and report exact evidence without weakening any check.
argument-hint: Optional scope, e.g. a path, package, or the change to verify
agent: agent
---

# Verify a change and report evidence

Prove that the current change does what it claims. Verification is read-only:
do not reformat, regenerate, or edit files to make a check pass.

## Input

- The user-supplied argument narrows the scope (a path, package, or feature).
  When it is empty, verify the working-tree changes against the last commit.
- The project's declared commands, read from its contributing guide, task
  runner, or project facts file.

## Procedure

1. Load [kit-verify-change](../skills/kit-verify-change/SKILL.md) and follow
   its evidence rules.
2. Identify what changed: list modified files and the behavior each one
   affects. Read the project's declared test, lint, type, and completion
   commands; never invent a command when one is declared.
3. Run the smallest relevant test first (the changed module's tests). Record
   the exact command, working directory, and result.
4. Run static checks that cover the changed files: types, lint, format check,
   and architecture or contract checks when the project declares them.
5. Exercise negative paths that the change touches: invalid input, error
   propagation, permission denial, and empty or boundary values. Add a missing
   regression only when the user asked for fixes; otherwise report the gap.
6. Run the declared completion gate once after the last edit.
7. Classify every result as executed-pass, executed-fail, inspected-only, or
   unavailable (with the missing prerequisite).
8. On a failure, report the first actionable error and its likely cause; do
   not lower thresholds, skip tests, or add ignores.

## Acceptance gates

- [ ] Every claim of "passes" has an executed command in this session.
- [ ] Failures are reported verbatim (trimmed to the relevant lines).
- [ ] Nothing was edited to satisfy a check without being reported.
- [ ] Runtime behavior that a file test cannot prove is labeled unverified.

## Output

A table with columns: check, command, result, notes. Then a short list of
untested risks and the next action. End with a one-line verdict:
`verified`, `failed`, or `partially verified`.
