---
description: Align tests for a module with its behavior contract by adding missing negative cases, removing flakiness, and fixing names without weakening assertions.
argument-hint: Module, package, or test directory to align
agent: agent
---

# Align tests with the behavior they protect

Bring the tests for one area in line with its observable contract. The goal is
tests that fail for the right reason, not a higher line count.

## Input

- The user-supplied argument names the module, package, or test directory.
  When it is empty, use the files changed in the working tree and their tests.

## Procedure

1. Load [kit-test-first](../skills/kit-test-first/SKILL.md); it owns test
   layers, naming, factories, determinism, and hygiene checks.
2. Read the production code and list its observable behaviors: return values,
   raised errors, side effects, and boundary rules. Mark each as covered,
   partially covered, or missing by reading the existing tests.
3. Run the existing tests for the area first and record the baseline result.
   Do not proceed on a red baseline without reporting it.
4. For each missing behavior, write a test at the narrowest layer that can
   observe it, named after behavior and outcome. Prioritize invalid input,
   boundary values, and failure recovery.
5. Prove every new test fails for the intended reason against a deliberately
   broken copy of the behavior, or explain why that is not possible.
6. Replace sleeps, wall-clock time, real network, and shared mutable state with
   seams, fixed clocks, and fixtures. Fix flakiness at its source.
7. Replace private-call choreography assertions with assertions on results and
   effects, keeping the same strength.
8. Rename generic or numbered tests to behavior names; keep one module per
   behavior area.
9. Run the hygiene and naming checks that the skill provides over the touched
   test directories, then the area's tests, then the declared completion gate.

## Acceptance gates

- [ ] No assertion was deleted or loosened; every removal is justified in the
      report.
- [ ] Each new test has a recorded red reason.
- [ ] Tests are deterministic: no sleeps, live services, or unseeded randomness.
- [ ] The area's tests and the completion gate pass.

## Output

A coverage table (behavior, test, status before, status after), the list of
files changed, commands run with results, and remaining gaps that need a
broader integration test or a product decision.
