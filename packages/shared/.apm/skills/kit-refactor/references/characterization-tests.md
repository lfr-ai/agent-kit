# Characterization tests

A characterization test records what code **currently does**, not what it
should do. It is the safety net for refactoring code that has weak or no tests:
you pin today's behavior, refactor, and the test tells you if anything
observable moved. Defects found along the way are recorded, not fixed in the
same change.

## Procedure

1. **Choose the boundary.** Test at the level callers observe: a public
   function, a command-line entry point, an HTTP handler, a message consumer.
   Avoid private helpers; their shape is exactly what the refactoring changes.
2. **Find a seam.** A seam is a place where you can substitute a dependency
   without editing the code under test: a parameter, a constructor argument, an
   injected clock, a configuration value, an environment variable, a module
   attribute a test can replace. If none exists, create the smallest one (pass
   a clock instead of reading the system time) as the first, separately
   reviewed step.
3. **Control non-determinism.** Fix time, random seeds, generated identifiers,
   locale, time zone and ordering of unordered collections. Replace network and
   external services with fakes at the seam.
4. **Write a test with a deliberately wrong expectation**, run it, and copy the
   actual value from the failure into the assertion. This is the core move: the
   code tells you what it does.
5. **Cover the input space that matters**: ordinary values, boundaries (empty,
   zero, maximum, one past maximum), invalid input and the error raised, and
   each branch you intend to touch. Use coverage data to find branches the
   characterization misses.
6. **Name tests after observed behavior** (`test_total_rounds_half_up_to_cents`)
   so a later reader knows what was pinned and why.
7. **Mark surprising behavior** with a comment or a separate test name such as
   `test_negative_quantity_is_currently_accepted` and log it as a defect. Do not
   change it while refactoring.

## Golden master (approval) testing

When outputs are large (reports, rendered documents, generated code, API
payloads), capture the whole output once and compare later runs to it:

1. Generate a broad, deterministic set of inputs (combinations of the
   parameters that matter, or recorded real inputs with sensitive data removed).
2. Run the current code and store each output as an approved file next to the
   test, in a stable text format with sorted keys and normalized line endings.
3. On every run, regenerate and compare; on a difference, show a diff and fail.
4. Approve a new output only on purpose, in its own reviewed commit.

Keep approved files small enough to review. A golden master that nobody can
read approves defects silently.

## Property-based characterization

For pure functions, compare the old and new implementation directly: keep the
old function temporarily, generate many inputs, and assert both return the same
result (or raise the same exception type). Delete the old function and this
comparison test when the refactoring is complete.

## What to pin, beyond return values

| Observable | How to pin it |
| --- | --- |
| Exceptions | type and the parts of the message callers parse |
| Side effects | calls recorded on a fake: count, order, arguments |
| Persistence | rows or documents written, read back through the public API |
| Logs used by operators or alerts | logger name, level, structured fields |
| Timing contracts | that work happens before or after a callback, not wall-clock duration |
| Serialization | exact bytes or canonical JSON for anything stored or sent |

## Pitfalls

- **Pinning implementation instead of behavior**: asserting that a private
  helper was called makes every refactoring fail. Assert results and external
  effects.
- **Mocking what you are refactoring**: replace only dependencies at the seam,
  never parts of the code under test.
- **Flaky characterization**: an unstable test is worse than none during a
  refactoring because it trains you to ignore failures. Fix the source of
  non-determinism first.
- **Fixing bugs mid-refactor**: a behavior change hidden in a refactoring
  commit cannot be reviewed or reverted separately.
- **Keeping scaffolding forever**: temporary comparison tests and duplicate old
  implementations are deleted at the end; durable characterization tests that
  describe real contracts stay.

## Sources

- [Michael Feathers, Working Effectively with Legacy Code (publisher page)](https://www.oreilly.com/library/view/working-effectively-with/0131177052/)
- [pytest: how to use fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)
- [pytest: monkeypatch](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)
- [Hypothesis documentation](https://hypothesis.readthedocs.io/)
- [coverage.py branch measurement](https://coverage.readthedocs.io/en/latest/branch.html)
