---
name: kit-test-first
description: Use when a requested behavior can be captured as a failing regression before implementation.
license: MIT
---

# Specify behavior before changing code

## Procedure

1. Translate the request into an externally observable result and the relevant boundary.
   List the examples as test names first in the [behavior cases](assets/cases.md.template)
   worksheet: ordinary, highest-risk boundary or invalid input, failure or recovery.
2. Find the narrowest existing test layer that can observe that result without faking the
   policy ([test tiers](references/test-tiers.md)). For a new or reorganized suite,
   lay out tiers, conftest layers, markers, tier sessions and coverage per
   [test suite architecture](references/test-suite-architecture.md), starting from
   the [nox template](assets/noxfile.py.template).
3. Write one test. Name it after the behavior and outcome, not the function
   ([naming guidance](references/naming-speed-coverage.md)).
4. Assert returned values, side effects, and error meaning rather than private call
   choreography. Build data with valid-by-default [factories](assets/factories.py.template)
   and receive context through fixtures ([fixtures and factories](references/fixtures-and-factories.md)).
5. Run the new test against current code and confirm it fails for the intended reason;
   an import, fixture or syntax error is not a valid red
   ([red, green, refactor](references/red-green-refactor.md)).
6. Implement the smallest change that makes the contract hold.
7. Refactor production and test code while green; re-run after each small step.
8. Re-run the regression and related tests; investigate unexpected failures rather than
   weakening assertions.
9. Add a property test when a rule should hold across an input space (round trips,
   invariants, bounds, model comparison) using the
   [property test template](assets/test_property.py.template) and
   [property-testing guidance](references/property-testing.md).
10. Add broader integration coverage only where the behavior crosses another real boundary.
11. Use synthetic data and deterministic time/network seams; avoid live services and
    credentials. Start new suites from the [`pytest.ini`](assets/pytest.ini.template) and
    [`conftest.py`](assets/conftest.py.template) templates (strict markers, warnings as
    errors, seeded randomness, fixed clock, network guard).
12. Remove nondeterminism at its source when a test is flaky
    ([flaky tests](references/flaky-tests.md)); never add sleeps or blind reruns.
13. Run the static hygiene checks on touched test directories:
    - [`check_test_hygiene.py`](assets/check_test_hygiene.py) (`python check_test_hygiene.py tests`):
      heavy module-level imports, sleeps, duplicate test module names;
    - [`check_test_naming.py`](assets/check_test_naming.py) (`python check_test_naming.py tests`):
      generic, numbered, too-short and redefined test names;
    - [`check_test_layout.py`](assets/check_test_layout.py) (`python check_test_layout.py tests`):
      test modules outside tier directories, test files not named `test_*.py`, and tests
      without an assertion or `pytest.raises`.
14. Report any test that could not run and the reason.

For a pure restructuring, first establish the pre-change behavior as a baseline
with characterization tests that pass against the unchanged code.

## Acceptance gates

- The new test failed before the change for the intended reason and passes after it;
  both runs are recorded with exact commands.
- A deliberate defect in the new code makes at least one test fail.
- Ordinary, boundary or invalid, and failure or recovery cases observe public results.
- Tests pass alone, in any order, and without network, real time or developer settings.
- `check_test_hygiene.py`, `check_test_naming.py` and `check_test_layout.py` report no new
  findings in touched files.
- Coverage thresholds are unchanged; new branches are exercised in both directions.
- Live or integration coverage that could not run is reported as unavailable, not passed.

Use the [regression design](references/guide.md) as the short entry point.
