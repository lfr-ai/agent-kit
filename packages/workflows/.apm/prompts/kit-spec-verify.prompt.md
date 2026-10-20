---
description: Verify an applied spec change scenario by scenario with reproducible evidence, design deviations, and impact items, recording pass or fail honestly.
argument-hint: Change folder path or identifier
agent: agent
---

# Verify a spec change

Prove each scenario of the change at an exact revision and record the outcome
so another reviewer can reproduce it.

## Input

- The user-supplied argument is the change folder path or identifier. When it
  is empty, list change folders whose tasks are all ticked and ask which one.

## Procedure

1. Load [kit-spec-workflow](../skills/kit-spec-workflow/SKILL.md) and follow
   the [verify stage](../skills/kit-spec-workflow/references/stage-verify.md).
2. Check entry criteria: all tasks ticked or deferred and the checker passes.
   Identify the exact revision or artifact under verification.
3. Copy the verification template into the folder if it is not there.
4. For each scenario of each active requirement, record one row: requirement,
   scenario, method (automated test or manual check), the exact command or
   steps, and the observed result.
5. Run the full automated suite at the identified revision and record the
   command, environment, and outcome.
6. Check the non-functional targets the design states, using the method it
   names.
7. Compare the implementation with the design. List every deviation and
   whether it was accepted.
8. Confirm the proposal's impact items: documentation, configuration,
   migrations, and client notices.
9. Confirm that behavior marked for removal is really gone.
10. Set the result to pass only when every row passed. Otherwise set fail,
    list the failing rows, and reopen plan or apply with the evidence.
11. If the same scenario fails twice, stop and escalate instead of patching
    around the test.

## Acceptance gates

- [ ] Every scenario has a row with reproducible evidence.
- [ ] Manual checks name the role, data set, and exact observation.
- [ ] No unexplained deviation from the design remains.
- [ ] The recorded result matches the rows; the checker passes.

## Output

The verification table, deviations, impact checklist, the overall result, and
the owner acceptance still needed. Offer the `kit-spec-archive` prompt when
the result is pass.
