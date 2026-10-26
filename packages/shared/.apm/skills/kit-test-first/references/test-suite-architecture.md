# Test suite architecture

The layout of a test suite decides how fast feedback is, which tests run where,
and whether a reader can find the test for a behavior. This page ties the
layout, names, fixtures, markers, environments, coverage and flaky-test policy
together; the linked references hold the detail. Review date: 2026-10-23.

## Directory layout

```text
tests/
  conftest.py          # suite-wide: markers by directory, clock, network guard
  factories.py         # test data builders shared by all tiers
  fakes.py             # in-memory implementations of owned ports
  unit/                # one rule or use case; no I/O except tmp_path
    conftest.py        # unit-only fixtures
  property/            # Hypothesis invariants
  contract/            # one abstract suite per port; fake and real subclasses
  integration/         # real boundaries: database, subprocess, HTTP, files
    conftest.py        # disposable services, per-test cleanup
  e2e/                 # the deployed system through its public interface
```

| Tier | Directory | Marker | Runs | Budget |
| --- | --- | --- | --- | --- |
| Unit | `tests/unit` | `unit` (applied by directory) | every save, pre-commit | milliseconds per test |
| Property | `tests/property` | `property` | every change | about a second per test in the dev profile |
| Contract | `tests/contract` | `unit` for fakes, `integration` for real adapters | every change / before merge | as its tier |
| Integration | `tests/integration` | `integration` | before merge, CI | seconds |
| End-to-end | `tests/e2e` | `e2e` | after deploy, scheduled | as needed; never destructive |

Mirror the source package inside each tier only when the suite is large
(`tests/unit/billing/test_invoice.py`); otherwise keep tiers flat. Tier
selection rules are in [test tiers](test-tiers.md).

[check_test_layout.py](../assets/check_test_layout.py) enforces the floor:
test modules live in a tier, test files are named `test_*.py`, and every test
asserts something.

```text
python check_test_layout.py tests
python check_test_layout.py tests --tier unit --tier integration
```

## Naming

- Modules: `test_<subject>.py`, one subject per module.
- Functions: `test_<behavior>_<condition>`, for example
  `test_refund_is_rejected_when_invoice_is_unpaid`. The name states the
  expected outcome so the failure report reads as a broken requirement.
- Classes only to share fixtures for one subject (`class TestRefund:`).

See [naming, speed and coverage](naming-speed-coverage.md) and the
`check_test_naming.py` asset.

## Fixtures and conftest layering

| Layer | Holds | Scope |
| --- | --- | --- |
| `tests/conftest.py` | marker assignment by directory, fixed clock, seeded randomness, network guard, shared factories | function unless expensive and immutable |
| `tests/<tier>/conftest.py` | tier-specific resources (fakes for unit, containers or databases for integration) | session for disposable services, function for state |
| test module | fixtures used by one module only | function |

Rules: fixtures return ready-to-use objects, not setup flags; teardown uses
`yield`; a session-scoped resource is never mutated by a test without a
per-test rollback. Builders and fakes are in
[fixtures and factories](fixtures-and-factories.md).

## Markers

Register every marker in the pytest configuration with `--strict-markers`;
apply tier markers by directory in the root `conftest.py` rather than by hand.
Add `slow` for opt-in tests and `e2e` when that tier exists. Select with
expressions (`-m "unit or property"`).

## Environments: tox or nox

Use one runner that wraps the same commands CI calls:

| Need | tox | nox |
| --- | --- | --- |
| Declarative, INI-style environments | yes | no |
| Python logic in session definitions | limited | yes |
| Locked installs with uv | `tox-uv` runner with the lockfile | `uv sync --locked` in the session |

Define one environment or session per tier plus a coverage session; start from
the [nox template](../assets/noxfile.py.template). The task runner or CI calls
these, never a hand-copied pytest command.

## Coverage

- Measure branches (`branch = true`), not only lines.
- Set `fail_under` in the coverage configuration once; never lower it to pass.
- Run coverage over unit, property and integration tiers together; end-to-end
  tests do not count towards the threshold.
- Exclude only generated code and `if TYPE_CHECKING:` blocks, each with a
  reason. Coverage shows what ran, not what was checked: the `no-assertion`
  rule and mutation testing cover the gap.

## Flaky test policy

1. A test that fails intermittently is a defect with an owner, not noise.
2. Reproduce with repeated runs and random order; find the nondeterminism.
3. Fix the cause (clock, order, shared state, network, timing). If the fix is
   not immediate, quarantine with a marker that names the issue and a removal
   date; quarantined tests still run and report, but do not block.
4. Never add blind retries or sleeps. See [flaky tests](flaky-tests.md).

## Test data builders

Use valid-by-default builders with keyword overrides so each test states only
what matters to it; keep them in `tests/factories.py` and the
[factories template](../assets/factories.py.template).

## Primary sources

- pytest, [Good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- pytest, [Fixtures reference](https://docs.pytest.org/en/stable/reference/fixtures.html)
- Hypothesis, [Settings and profiles](https://hypothesis.readthedocs.io/en/latest/reference/api.html#settings)
- coverage.py, [Configuration reference](https://coverage.readthedocs.io/en/latest/config.html)
- nox, [Usage](https://nox.thea.codes/en/stable/usage.html) and tox, [User guide](https://tox.wiki/en/latest/user_guide.html)
- Martin Fowler, [Test pyramid](https://martinfowler.com/bliki/TestPyramid.html)
