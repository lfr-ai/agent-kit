# Small tests that pin the contract

## Red, green, refactor

Write one observable example at the narrowest existing layer. Run it against the
old implementation: a failure caused by import setup or a missing dependency is
not the intended red. Implement the smallest complete behavior, rerun the test,
then simplify while preserving its assertion.

Use synthetic data, a deterministic clock seam and controlled network/process
boundaries. Mock external effects where needed, not the domain rule under test.
Use existing factories and framework conventions rather than adding a new test
library for one behavior.

## Quality gates

- A deliberate implementation defect makes the regression fail.
- Ordinary and highest-risk invalid/boundary cases observe public results.
- Error translation, atomicity and recovery are covered where behavior changes.
- Tests run independently without order, global settings or real credentials.
- Integration coverage exercises an actual changed boundary, not just two mocks.
- Coverage thresholds remain unchanged; line coverage alone is not correctness.

## Failure and recovery

Do not retry a flaky assertion until it passes. Isolate the nondeterministic
dependency, record the failure and fix its cause. If the required service cannot
be run safely, retain the offline contract test and mark live coverage unavailable.
Do not replace a failing security or data-loss assertion with a weaker one.

## Deeper references

- [Red, green, refactor](red-green-refactor.md)
- [Test tiers: unit, property, integration](test-tiers.md)
- [Fixtures and factories](fixtures-and-factories.md)
- [Property-based testing with Hypothesis](property-testing.md)
- [Preventing and fixing flaky tests](flaky-tests.md)
- [Test naming, speed hygiene and coverage](naming-speed-coverage.md)
- [Test suite architecture](test-suite-architecture.md)

## Sources

- pytest, [Good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
