# Testing through ports: fakes, contract tests and the signature checker

## Pick the double by what you need to observe

| Double | What it is | Use it for | Risk |
| --- | --- | --- | --- |
| Fake | Working, simplified implementation with state | Use-case tests; local runs | Drifts from production unless contract-tested |
| Stub | Returns canned answers | One branch of an adapter (e.g. an HTTP 503) | Says nothing about state |
| Mock | Records calls for assertions on interactions | Verifying an effect that has no observable state | Couples tests to call choreography |
| Real adapter on a disposable resource | Production code against a temp file, container or sandbox | Adapter contract and integration tests | Slower; needs setup |

Prefer fakes for application tests and real adapters for adapter tests. Use
mocks sparingly; when you do, use `unittest.mock.create_autospec` against the
port so a renamed parameter fails the test instead of silently passing.

## Writing a good fake

[`fake_adapters.py.template`](../assets/fake_adapters.py.template) shows the
pattern:

- Implement the full port, including its documented errors
  (`InvoiceNotFoundError`, `DuplicateInvoiceError`).
- Emulate the guarantees callers rely on: the in-memory unit of work stages
  changes and publishes them only on `commit`, so a use case that forgets to
  commit fails its test.
- Make failure configurable with plain fields (`declined_invoices`,
  `unavailable_attempts`, `fail=True`) rather than callbacks.
- Expose observable state (`committed`, `charges`, `sent`) for assertions.
- Keep fakes in one module and import them; do not redefine ad-hoc fakes in
  each test file.

## One contract suite, every implementation

A contract test states what *any* implementation of a port must do and runs
against each implementation:

- [`test_repository_contract.py.template`](../assets/test_repository_contract.py.template):
  an abstract `InvoiceRepositoryContract` class with all behavior tests and two
  subclasses that only provide a `unit_of_work` fixture (in-memory, SQLite).
- [`test_payment_contract.py.template`](../assets/test_payment_contract.py.template):
  the HTTP adapter driven by a recording transport that replays every documented
  provider answer, plus shared expectations parametrized over fake and real.

Contract suites should cover: the happy path round trip, not-found and
duplicate errors, transaction visibility (commit, rollback, exit without
commit), ordering and limits, and error translation for every documented
failure class. If the real adapter needs a server, mark that subclass with the
integration marker and run it in the slower tier; the fake subclass still runs
in every unit run.

## Testing driving adapters

Driving adapters translate input to commands and results to responses. Test
them with a fake use case (any callable with the right signature) and assert on
the translation: status codes, exit codes, error bodies, argument parsing. Do
not re-test business rules through them.

## Keeping fakes and adapters in sync automatically

Tests prove behavior; [`check_ports_adapters.py`](../assets/check_ports_adapters.py)
proves shape. It parses source (no imports, no execution) and for every
Protocol under `--ports` reports, per implementation:

- members the port declares but the class lacks;
- a synchronous method where the port is `async` (or the reverse);
- parameter name, order or kind differences (positional-only, keyword-only,
  `*args`, `**kwargs`);
- a default the port declares but the implementation drops, an extra default,
  or a different literal default (`...` in a port means "some default");
- public methods the port does not declare (silence with `--allow-extra NAME`
  or `--ignore-extra`);
- ports with no implementation at all (`--allow-unimplemented`).

Implementations are classes that name the port as a base, plus any class that
structurally defines every port member (disable with `--explicit-only`). Base
classes found in the scanned paths are followed, so an adapter inheriting a
shared base is checked against its effective members. Return types are
deliberately left to a type checker.

```text
python check_ports_adapters.py src tests --ports src/app/application/ports
python check_ports_adapters.py src --ports src/app/application/ports --allow-extra close
python check_ports_adapters.py --self-test
```

Limitations: classes are matched by simple name, so two ports with the same
name in different modules are ambiguous; dynamically created classes and
members added by decorators or metaclasses are invisible to static parsing.

## Sources

- Python documentation, [unittest.mock autospeccing](https://docs.python.org/3/library/unittest.mock.html#autospeccing)
- pytest, [How to use fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)
  and [How to parametrize fixtures and test functions](https://docs.pytest.org/en/stable/how-to/parametrize.html)
- Python documentation, [ast: Abstract Syntax Trees](https://docs.python.org/3/library/ast.html)
- Python typing specification, [Protocols](https://typing.python.org/en/latest/spec/protocol.html)
