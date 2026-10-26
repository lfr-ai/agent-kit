---
description: Plan and apply one measured modernization batch (Python version, dependencies, packaging, or syntax) with verification, rollback, and a modernization ledger.
argument-hint: Modernization goal, e.g. "Python 3.13", "pyproject migration", or "typing syntax"
agent: agent
---

# Modernize one batch at a time

Move the codebase forward without mixing upgrades with behavior changes. Each
batch has one reason, is verified on its own and can be reverted on its own.

## Input

- The user-supplied argument names the goal: a target Python version, a
  dependency or group to upgrade, a packaging migration, or a syntax family.
  When it is empty, produce the baseline and a batch plan only; change nothing.
- The project's declared commands, read from its contributing guide, task
  runner or project facts file.

## Procedure

1. Load [kit-modernize](../skills/kit-modernize/SKILL.md) and follow its
   procedure, tiers and gates.
2. Record the baseline in the modernization ledger: current and target Python
   with support status, outdated direct dependencies, first-party deprecation
   warnings, and the legacy-syntax count from the skill's checker.
3. Split the goal into batches by tier: tooling, runtime minor upgrades,
   interpreter, majors and replacements, then mechanical syntax rewrites.
   Present the plan; apply only the first batch unless the user approved more.
4. Change dependencies only through the project's manifest and lockfile
   workflow, and audit the new lock before installing it.
5. For syntax batches, apply one Ruff rule family at a time and review every
   unsafe fix by hand, paying attention to code that reads annotations or enum
   string values at runtime.
6. Verify the batch: focused tests, full suite, deprecation warnings as errors,
   type checker, lint, lock consistency, and a wheel install away from the
   checkout. The legacy-syntax count must not rise.
7. On failure, revert the whole batch including the lockfile, record the
   evidence in the ledger and propose a smaller batch.
8. Update the ledger with before and after evidence and the gate that prevents
   regression.

## Acceptance gates

- [ ] The batch has one reason and contains no behavior change or unrelated
      cleanup.
- [ ] `requires-python`, CI matrix, tool target versions and the lockfile agree.
- [ ] Every verification command ran in this session with its result recorded.
- [ ] The rollback path is stated and was not needed, or was exercised.

## Output

The batch plan, the commands run with results, the ledger rows added or
updated, and the next proposed batch.
