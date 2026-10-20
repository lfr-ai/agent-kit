# Test naming, speed hygiene and what coverage means

## Names are the first line of every failure report

A good test name states the situation and the expected outcome, so a failing
run reads like a broken requirement:

| Weak | Better |
| --- | --- |
| `test_1`, `test_it`, `test_works` | `test_paid_invoice_cannot_be_voided` |
| `test_settle` | `test_settling_twice_charges_once_and_reports_already_paid` |
| `test_error` | `test_unknown_invoice_is_reported_without_charging` |
| `test_parse_ok` | `test_amount_with_two_decimals_is_parsed_exactly` |

Patterns that work: `test_<subject>_<behavior>`,
`test_<situation>_<expected outcome>`, or `test_<when>_<then>`. Pick one per
codebase. Class-grouped tests (`class TestInvoice:`) may drop the subject from
each method name.

[`check_test_naming.py`](../assets/check_test_naming.py) enforces a floor:

```text
python check_test_naming.py tests                     # at least 3 words after 'test'
python check_test_naming.py tests --min-words 4 --forbid test_happy_path
python check_test_naming.py tests --allow test_smoke
python check_test_naming.py --self-test
```

It reports generic names from a built-in list, numbered names (`test_1`,
`test_case_2`), names with too few words, and the same test name defined twice
in one module or class (Python keeps only the last definition, so the first test
silently never runs).

## Speed hygiene

A suite people run on every save must finish in seconds. Common sources of
slowness, and what to do:

- **Heavy imports at collection time.** Every module-level import in a test
  file is paid by every run, even for deselected tests. Import heavy libraries
  inside the test or fixture, or use `pytest.importorskip`.
- **Sleeping.** Replace with explicit waits or a fake clock.
- **Real I/O in unit tests.** Use fakes; keep real I/O in the integration tier.
- **Over-wide fixture setup.** Building a database per test when one schema per
  session plus a transaction rollback per test would do.
- **Too many property examples in the inner loop.** Use a small dev profile and
  a larger CI profile.
- **Duplicate test module names.** Without packages or `--import-mode=importlib`
  pytest cannot import both, and workarounds tend to add slow path hacks.

[`check_test_hygiene.py`](../assets/check_test_hygiene.py) reports the static
ones:

```text
python check_test_hygiene.py tests
python check_test_hygiene.py tests --heavy-module my_big_sdk --no-default-heavy
python check_test_hygiene.py tests --allow-sleep --allow-duplicate-basenames
python check_test_hygiene.py --self-test
```

Measure the dynamic ones with `--durations=10` (already in the
[`pytest.ini.template`](../assets/pytest.ini.template)) and fix the top entries
first.

## What coverage does and does not tell you

- **Line coverage** shows which statements ran. **Branch coverage** also shows
  whether each decision went both ways; enable it (`--cov-branch` with
  pytest-cov, or `branch = true` in coverage configuration). A fully covered
  `if` without its `else` path is a common hiding place for bugs.
- Coverage proves code *executed*, not that its result was *checked*. A test
  without assertions can reach 100 %.
- Use coverage to find **untested behavior**, then write a test that asserts
  it. Do not write tests to raise a number.
- Keep thresholds stable and ratchet them up; never lower a threshold to pass a
  gate. Exclude only code that cannot run in tests (`if TYPE_CHECKING:`,
  `raise NotImplementedError` in abstract methods, `if __name__ == "__main__":`)
  and say why.
- Mutation testing tools answer the stronger question "would a test fail if
  this line were wrong?". Use them occasionally on critical modules.

## Sources

- pytest, [Conventions for Python test discovery](https://docs.pytest.org/en/stable/explanation/goodpractices.html#conventions-for-python-test-discovery)
- pytest, [How to invoke pytest: profiling test execution duration](https://docs.pytest.org/en/stable/how-to/usage.html#profiling-test-execution-duration)
- pytest, [pytest.importorskip](https://docs.pytest.org/en/stable/reference/reference.html#pytest-importorskip)
- coverage.py, [Branch coverage measurement](https://coverage.readthedocs.io/en/latest/branch.html)
  and [Excluding code from coverage](https://coverage.readthedocs.io/en/latest/excluding.html)
