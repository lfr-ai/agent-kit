# Preventing and fixing flaky tests

A flaky test passes and fails on the same code. It erodes trust in the whole
suite: people rerun until green and stop reading failures. Treat a flaky test as
a bug in the test or the code, never as noise.

## Common causes and their fixes

| Cause | Symptom | Fix |
| --- | --- | --- |
| Real time | fails near midnight, month end, DST change, or on slow machines | inject a clock; pass aware fixed timestamps |
| Sleeping instead of waiting | fails under load, slow in general | wait on an event/condition with a timeout; use a fake clock |
| Order dependence | passes alone, fails in the full run (or the reverse) | build state per test; reset globals in fixtures |
| Shared resources | fails in parallel runs | unique `tmp_path`, unique database/queue names per test or worker |
| Randomness | fails on some seeds | seed explicitly, or use Hypothesis so failures shrink and replay |
| Network and external services | timeouts, rate limits | fakes or recorded transports in unit tests; isolated local services in integration |
| Unordered collections | assertion compares a set or dict order | compare as sets or sort before comparing |
| Floating point | off-by-epsilon | `pytest.approx` or exact `Decimal` arithmetic |
| Concurrency | rare deadlocks or lost updates | deterministic schedulers, explicit synchronization, stress tests in a separate tier |
| Environment leakage | depends on developer settings, locale, time zone | clear app variables with `monkeypatch`; set locale-independent formatting |
| Resource leaks | later tests fail with "too many open files" or warnings | close in fixtures; `filterwarnings = error` surfaces `ResourceWarning` |

## Built-in prevention

The templates in this skill already prevent many causes:

- [`conftest.py.template`](../assets/conftest.py.template): seeded `random`,
  environment cleanup, a network guard for non-integration tests, a fixed clock.
- [`pytest.ini.template`](../assets/pytest.ini.template): warnings as errors,
  strict markers and configuration, `xfail_strict`, a faulthandler timeout that
  dumps stack traces of hung tests.
- [`check_test_hygiene.py`](../assets/check_test_hygiene.py): reports
  `time.sleep` and non-zero `asyncio.sleep` in tests, and duplicate test module
  names that make collection depend on import order.

## Diagnosing a flaky test

1. Reproduce: run the single test in a loop and the whole file in random order.
   Record the seed, worker id and environment of each failure.
2. Classify the cause using the table above. Read the failing assertion and
   logs before changing anything.
3. Make it deterministic: remove the source of nondeterminism rather than
   widening a timeout or adding a retry.
4. Prove it: run the previously failing loop again many times.
5. Keep the evidence (seed, failure output) in the fix description.

## Rules

- No automatic reruns as a fix. A rerun plugin may be used to *detect* and
  report flakiness, never to turn a red build green silently.
- No `sleep` to wait for something; wait for the thing.
- No skips without a reason and an owner; `xfail` with `strict = true` for known
  bugs so the test alerts you when the bug is fixed.
- Quarantine only with a tracking issue and a deadline; quarantined tests still
  run and report, they just do not block.
- Async tests: await the condition (`asyncio.Event`, `asyncio.wait_for`) and
  set explicit timeouts so a hang fails quickly instead of blocking CI.

## Sources

- pytest, [Flaky tests](https://docs.pytest.org/en/stable/explanation/flaky.html)
- pytest, [How to capture warnings](https://docs.pytest.org/en/stable/how-to/capture-warnings.html)
- pytest, [Configuration options reference](https://docs.pytest.org/en/stable/reference/reference.html#ini-options-ref)
- Python documentation, [faulthandler](https://docs.python.org/3/library/faulthandler.html)
  and [asyncio synchronization primitives](https://docs.python.org/3/library/asyncio-sync.html)
- Hypothesis, [Flaky failures](https://hypothesis.readthedocs.io/en/latest/tutorial/flaky.html)
