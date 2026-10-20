# Red, green, refactor

Test-first development is a short loop that turns a requested behavior into
an executable example before any production code changes. Each turn should
take minutes, not hours.

## The loop

1. **List examples.** Write the behaviors as one-line test names first:
   ordinary case, the boundary most likely to break, the failure or recovery
   case. Use the [behavior cases worksheet](../assets/cases.md.template).
2. **Red.** Write one test for the simplest example at the narrowest layer that
   can observe it. Run it and read the failure. It must fail *because the
   behavior is missing* - an assertion about the result, or a missing
   attribute you are about to add. An `ImportError` from a typo, a fixture
   error or a syntax error is not a valid red; fix the test until it fails for
   the intended reason.
3. **Green.** Write the smallest production change that makes this test pass.
   Hard-coding is acceptable for one example; the next example forces the
   generalization. Do not add behavior no test asks for.
4. **Refactor.** With all tests green, remove duplication and improve names in
   both production and test code. Run the tests after each small step. Do not
   change behavior during refactoring; if you need to, go back to red.
5. **Repeat** with the next example. Commit (or checkpoint) at green.

## Choosing the next test

- Go from degenerate to general: empty input, one item, many items.
- Go from happy path to the failure paths that change the contract (not found,
  invalid, duplicate, timeout).
- Prefer a test that forces a *new* decision in the code over one that would
  pass already. If a new test passes immediately, either the behavior already
  existed (keep the test as documentation if it adds clarity) or the test
  asserts too little.

## Where to write the test

| Behavior lives in | Write the first test against | Doubles |
| --- | --- | --- |
| A pure rule (validation, calculation, state transition) | the domain function or entity | none |
| Orchestration of several collaborators | the use case | fakes for driven ports |
| Translation to/from a technology | the adapter | the real technology on a disposable resource, or a recorded transport |
| Wiring and configuration | the composition root | safe settings, no external network |

Write the test at the highest of these layers that is still fast and
deterministic; go lower when the higher test cannot isolate the decision.

## Bugs follow the same loop

1. Reproduce the report as a failing test at the narrowest layer that shows it.
2. Confirm it fails for the reported reason (same wrong value, same exception).
3. Fix the cause, not the symptom; keep the test as a regression.
4. Ask whether the same mistake exists in sibling code; add cases there too.

## Characterization before refactoring legacy code

When code has no tests and you need to change its structure:

1. Write tests that pin the *current* observable behavior, including outputs
   you think are wrong (mark those with a comment and a ticket).
2. Run them against the unchanged code; they must pass.
3. Refactor in small steps, keeping them green.
4. Only then change behavior, test-first.

## Anti-patterns

- Writing many tests before any implementation: the design cannot respond to
  what the first test teaches.
- Asserting on private call order with mocks instead of on results; the tests
  break on every refactor and miss real bugs.
- Weakening an assertion to get to green. If the expectation was wrong, change
  it deliberately and say why in the commit.
- Skipping the refactor step until "later"; duplication then hardens.

## Sources

- pytest, [Get started](https://docs.pytest.org/en/stable/getting-started.html)
  and [Good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- pytest, [How to write and report assertions in tests](https://docs.pytest.org/en/stable/how-to/assert.html)
- Python documentation, [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
