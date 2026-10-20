# Structured logging

Logs are an operational interface. Make them structured, low-volume,
correlation-friendly, and free of secrets and personal data.

## Rules

1. Use the standard library: `import logging` and
   `logger = logging.getLogger(__name__)` at module level. Do not import names
   from `logging` (`from logging import getLogger`); the qualified form keeps
   call sites recognizable and is enforced by the bundled checker.
2. Configure handlers and formatters once, in the composition root or the
   process entry point. Library and service modules never call
   `logging.basicConfig` or attach handlers.
3. Pass values as lazy arguments or `extra`, never pre-formatted strings:
   `logger.info("order confirmed", extra={"order_id": order.id})`. Avoid
   f-strings in log calls; they format even when the level is disabled and hide
   structure from log processors.
4. Log a failure once, at the boundary that handles it. A layer that re-raises
   does not log; a layer that translates and re-raises does not log either.
5. Use `logger.exception(...)` only inside an `except` block where the
   exception is handled; it attaches the traceback automatically.
6. Choose levels by audience:
   - `DEBUG`: diagnostic detail for developers; off in production by default.
   - `INFO`: business-relevant state changes (order confirmed, job finished).
   - `WARNING`: degraded but handled situations (retry, fallback used).
   - `ERROR`: a request or job failed and someone may need to act.
   - `CRITICAL`: the process cannot continue.
7. Never log credentials, tokens, full request bodies, or personal data. Log
   identifiers that let an operator look the record up instead.

## Event shape

Use a stable, lowercase event message and put variable data in fields:

```python
logger.info(
    "invoice issued",
    extra={"invoice_id": invoice.id, "amount_minor": invoice.total.minor_units},
)
```

A JSON formatter then emits one object per line:

```json
{"ts": "2026-01-02T10:00:00+00:00", "level": "INFO", "logger": "billing.service",
 "event": "invoice issued", "invoice_id": "inv-42", "amount_minor": 1250,
 "correlation_id": "req-42"}
```

## Correlation

Store a request or job correlation identifier in a `contextvars.ContextVar` set
by the transport middleware, and add it to every record with a
`logging.Filter`. Context variables are task-local in `asyncio`, so concurrent
requests do not leak identifiers into each other.

## Template

[logging_setup.py.template](../assets/logging_setup.py.template) provides a JSON
formatter, a correlation filter, and an idempotent `configure_logging` function;
[test_logging_setup.py.template](../assets/test_logging_setup.py.template)
verifies the emitted fields with `caplog`-independent handler capture.

## Testing logs

- Assert on structured fields, not on formatted message text.
- Use pytest's `caplog` fixture for "was this event emitted" checks.
- Assert that secrets do not appear in any emitted record for code paths that
  handle them.

## Anti-patterns

| Anti-pattern | Why it hurts |
| --- | --- |
| `print` in service code | Bypasses levels, handlers, and redaction. |
| Logging then re-raising at every layer | Duplicate noise for one failure. |
| `logger.error(str(error))` | Loses the traceback and the exception type. |
| Catch-all `except Exception: logger.warning(...)` | Hides defects as warnings. |
| Building messages with f-strings | Eager formatting and unstructured output. |

## Sources

- [logging - Logging facility for Python](https://docs.python.org/3/library/logging.html)
- [Logging HOWTO](https://docs.python.org/3/howto/logging.html)
- [Logging Cookbook](https://docs.python.org/3/howto/logging-cookbook.html)
- [contextvars](https://docs.python.org/3/library/contextvars.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
