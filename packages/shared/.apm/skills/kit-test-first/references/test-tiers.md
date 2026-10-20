# Test tiers: unit, property and integration

Tiers exist so the inner loop stays fast while slower, broader evidence still
runs before merge. Each tier has an entry rule, a speed budget and a place in
the gate.

| Tier | Proves | May use | Must not use | Budget per test | Runs |
| --- | --- | --- | --- | --- | --- |
| Unit | one rule or one use case's decisions | fakes, `tmp_path`, injected clock | network, real services, sleeps, shared state | under ~50 ms | every save / pre-commit |
| Property | an invariant over a generated input space | Hypothesis strategies, pure code, fakes | I/O that makes examples slow | under ~1 s per test with the dev profile | every change |
| Integration | a real boundary works: SQL, HTTP wire format, subprocess, file layout | disposable databases, local servers, containers, recorded transports | production systems, shared mutable environments, real credentials | seconds | before merge / CI |
| End-to-end / smoke | the deployed system answers | the real deployment | destructive operations | as needed | after deploy |

## Mapping tiers to markers and directories

Register every tier as a marker ([`pytest.ini.template`](../assets/pytest.ini.template))
and apply it by directory in a root `conftest.py`
([`conftest.py.template`](../assets/conftest.py.template)), so authors cannot
forget the marker:

```text
tests/
  unit/          -> @pytest.mark.unit (applied automatically)
  property/      -> @pytest.mark.property
  integration/   -> @pytest.mark.integration
  conftest.py    -> markers, clocks, factories, isolation guards
  factories.py   -> test data builders
  fakes.py       -> in-memory port implementations
```

Select tiers with marker expressions:

```text
pytest -m "unit or property"        # inner loop
pytest -m integration               # boundary tier
pytest -m "not slow"                # everything fast
pytest --run-slow                   # opt in to tests marked slow
```

`--strict-markers` turns a misspelled marker into an error instead of a test
that silently never runs in its intended tier.

## Entry rules worth enforcing

- **Unit tests cannot reach the network.** The conftest template replaces
  `socket.connect` for non-integration tests and allows loopback only.
- **No real time.** Inject a clock port (`Callable[[], datetime]`) and pass a
  fixed value; never call `datetime.now()` in code under unit test.
- **No sleeps.** Waiting is replaced by explicit events, conditions or a fake
  clock (enforced by [`check_test_hygiene.py`](../assets/check_test_hygiene.py)).
- **No order dependence.** Each test builds its own state. Run single tests in
  isolation and, occasionally, the suite in a shuffled order to prove it.
- **Integration tests clean up.** Use fixtures with `yield` teardown, unique
  names per test (`tmp_path`, generated database names) and never share
  writable resources between parallel workers.

## Choosing a tier for a new test

1. Can the behavior be observed without I/O? Unit.
2. Is it a rule that should hold for a whole input space (round trips,
   idempotence, ordering, conservation)? Add a property test next to the
   example tests.
3. Does correctness depend on the real technology (SQL dialect, HTTP headers,
   file permissions, serialization library)? Integration, plus a unit test of
   the decision logic with a fake.
4. Never move a test to a slower tier just because it is hard to isolate; first
   try to introduce the missing port or seam.

## Contract tests span tiers

A contract suite (one abstract class, one subclass per implementation) runs
the fake in the unit tier and the real adapter in the integration tier. Mark
the real subclass with `@pytest.mark.integration` when it needs a service.

## Sources

- pytest, [How to mark test functions with attributes](https://docs.pytest.org/en/stable/how-to/mark.html)
- pytest, [Working with custom markers](https://docs.pytest.org/en/stable/example/markers.html)
- pytest, [Writing hook functions](https://docs.pytest.org/en/stable/how-to/writing_hook_functions.html)
- pytest, [How to use temporary directories and files in tests](https://docs.pytest.org/en/stable/how-to/tmp_path.html)
- Hypothesis, [documentation](https://hypothesis.readthedocs.io/en/latest/)
