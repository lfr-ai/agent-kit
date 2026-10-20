# Error handling

Errors are part of a service's contract. Callers must be able to tell expected
business outcomes from defects, and boundaries must translate failures into
their own vocabulary without leaking internals.

## Exception hierarchy

Give each package one base exception and a small number of specific subclasses
that callers actually handle differently:

```python
class BillingError(Exception):
    """Base class for expected billing failures."""


class InvoiceNotFoundError(BillingError):
    """No invoice exists for the requested identifier."""

    def __init__(self, *, invoice_id: str) -> None:
        """Record the missing identifier.

        Args:
            invoice_id: Identifier that was looked up.
        """
        super().__init__(f"invoice {invoice_id!r} was not found")
        self.invoice_id = invoice_id


class InvoiceAlreadyIssuedError(BillingError):
    """The invoice is already issued and cannot change."""
```

Rules:

- Name exceptions with an `Error` suffix and describe the condition, not the
  layer (`InvoiceNotFoundError`, not `RepositoryError`).
- Carry structured attributes (`invoice_id`) so boundaries can build responses
  without parsing messages.
- Use built-in exceptions for programming errors: `ValueError` for invalid
  arguments, `TypeError` for wrong types, `LookupError` subclasses for lookups.

## Where to raise, catch, and translate

| Layer | Responsibility |
| --- | --- |
| Domain | Raise domain errors when an invariant or precondition fails. |
| Application | Let domain errors propagate; translate port failures into application errors only if callers need a different meaning. |
| Infrastructure adapter | Catch vendor exceptions (driver, HTTP client, SDK) and raise the port's documented error, chaining with `from`. |
| Presentation | Map application and domain errors to the transport (HTTP status and problem details, CLI exit code). Log unexpected errors once. |

Always chain on translation so the original traceback survives:

```python
try:
    row = self._session.get(InvoiceRow, invoice_id)
except OperationalError as error:
    raise StorageUnavailableError(operation="get_invoice") from error
```

## Catch narrowly

- Catch the most specific exception you can handle. Never write bare `except:`.
- `except Exception` is acceptable only at a top-level boundary (request
  handler, job runner, CLI `main`) that logs once and converts to a generic
  failure response.
- Keep the `try` block minimal: only the call that can raise the handled error.
- Never `pass` in an `except` block without a comment explaining why ignoring
  is correct; prefer `contextlib.suppress(SpecificError)` for intent.

## Expected outcomes are not always exceptions

When "not found" or "rejected" is a normal result that most callers branch on,
return `X | None` or a small result union instead of raising. Raise when the
caller usually cannot continue.

## Partial side effects

Validate everything before mutating anything. When several writes must succeed
together, use the storage transaction (unit of work) and let an exception roll
it back. Do not leave half-written state for the caller to clean up.

## Retries

Retry only idempotent operations and only for transient failures (timeouts,
connection resets, explicit "retry later" responses). Bound attempts, use
exponential backoff with jitter, and surface the final failure.

## Messages

- Messages state what failed and with which identifier; they do not include
  secrets, tokens, or personal data.
- Public error responses never include stack traces or vendor messages.

## Exception groups

`ExceptionGroup` and `except*` are for concurrent work (for example
`asyncio.TaskGroup`) where several failures can occur together. Do not use them
to aggregate validation messages; return a structured list instead.

## Tests

For every documented error: one test that triggers it through the public API
and asserts type and attributes, plus a boundary test that asserts the mapped
transport response.

## Sources

- [Errors and exceptions tutorial](https://docs.python.org/3/tutorial/errors.html)
- [Built-in exceptions](https://docs.python.org/3/library/exceptions.html)
- [PEP 3134 - Exception chaining](https://peps.python.org/pep-3134/)
- [PEP 654 - Exception groups and except*](https://peps.python.org/pep-0654/)
- [contextlib.suppress](https://docs.python.org/3/library/contextlib.html#contextlib.suppress)
- [Ruff tryceratops rules](https://docs.astral.sh/ruff/rules/#tryceratops-try)
