# Fixtures and factories

Fixtures provide *context* (a database file, a clock, a fake gateway).
Factories provide *data* (an invoice with valid defaults). Keep the two apart:
tests read best when context arrives as fixture arguments and data is built
inline with only the relevant fields spelled out.

## Fixtures

- **Scope as narrowly as possible.** Function scope by default. Widen to
  `module` or `session` only for expensive, read-only resources (a compiled
  schema, a started local server), and never share mutable state across tests.
- **Teardown with `yield`.** Code after `yield` runs even when the test fails.
  Prefer built-ins that already clean up: `tmp_path`, `monkeypatch`, `caplog`,
  `capsys`.
- **Autouse sparingly.** Autouse fixtures are invisible at the call site; keep
  them for isolation guarantees that every test needs (seeded randomness,
  environment cleanup, the network guard) and put them in the root
  `conftest.py` ([`conftest.py.template`](../assets/conftest.py.template)).
- **Compose small fixtures.** `clock` depends on `fixed_now`; a test that needs
  a different time overrides `fixed_now` locally instead of rebuilding `clock`.
- **Override by proximity.** A fixture in `tests/integration/conftest.py`
  shadows the root one for that directory; a fixture defined in a test class
  shadows both for that class. Contract suites use this to swap implementations.
- **Parametrize fixtures** (`@pytest.fixture(params=[...])`) when every test
  using the fixture must run against each variant; parametrize *tests* when
  only one test varies.
- **Avoid fixture pyramids.** If understanding a test requires reading five
  fixtures, inline the important values.

## Factories

[`factories.py.template`](../assets/factories.py.template) shows the shape:

```python
def build_invoice(
    *,
    invoice_id=None,
    customer_id="cus-0001",
    amount=Decimal("100.00"),
    currency="EUR",
    status=InvoiceStatus.OPEN,
    payment_reference=None,
) -> Invoice: ...


def test_void_invoice_cannot_be_paid() -> None:
    invoice = build_invoice(status=InvoiceStatus.VOID)  # only the relevant field
    with pytest.raises(InvoiceError):
        invoice.mark_paid(payment_reference="pay-1")
```

Rules:

- Defaults are **valid** and boring; a test that needs an invalid value passes
  it explicitly so the reader sees it.
- Keyword-only overrides; no positional arguments.
- Unique identifiers come from a counter, not randomness, so failures are
  reproducible and readable (`inv-0007`).
- Derived fields stay consistent: a factory asked for a paid invoice also sets
  a payment reference.
- Build through the real constructor so invariants run; do not bypass
  validation with `object.__new__` or raw dictionaries.
- One factory module per test suite; expose it as a fixture
  (`make_invoice`) only when tests benefit from injection.

## Literal values in assertions

Assert against literals that state the expectation (`== Decimal("125.50")`),
not against values recomputed with the same logic as the production code. When
a default is part of the contract, read it from its canonical place in one
dedicated test instead of repeating it everywhere.

## Isolation checklist

- Every test can run alone: `pytest path::test_name`.
- Every test can run in any order and in parallel workers.
- No test reads the developer's environment, home directory or network.
- Files go to `tmp_path`; environment changes go through `monkeypatch`.
- Global state touched by the code under test (caches, registries, random
  seeds, logging configuration) is reset by a fixture.

## Sources

- pytest, [How to use fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)
- pytest, [Fixtures reference](https://docs.pytest.org/en/stable/reference/fixtures.html)
- pytest, [How to monkeypatch/mock modules and environments](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)
- pytest, [How to parametrize fixtures and test functions](https://docs.pytest.org/en/stable/how-to/parametrize.html)
