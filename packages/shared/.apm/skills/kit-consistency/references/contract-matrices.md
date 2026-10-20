# Contract matrices: proving one concept means the same thing everywhere

A contract matrix lists one concept (a field, an enum, an error, a default)
across every boundary it crosses, with one row per boundary and one column per
property that can drift. Fill it before changing the concept and keep it with
the change ([matrix template](../assets/contract-matrix.md.template)).

## Columns that catch real drift

| Column | Question | Typical drift |
| --- | --- | --- |
| Name and type | What is it called and typed as here? | `amount: Decimal` vs `amount: float` vs `"amount": "12.30"` |
| Missing / null / empty | What happens when it is absent, `null`, `""` or `[]`? | API treats missing as default, database stores NULL, domain rejects |
| Default | Who supplies the default and is it the same value? | `limit=100` in the port, `limit=50` in the adapter |
| Units and precision | Unit, scale, rounding, currency | cents vs major units; banker's vs half-up rounding |
| Time | Time zone, precision, format | naive local time in one layer, UTC in another |
| Allowed values | Enum members, ranges, length limits | new status added to the domain but not to the API schema |
| Case and normalization | Case sensitivity, trimming, Unicode normalization | e-mail compared case-sensitively in one place only |
| Error meaning | Which error/status signals which failure | not-found as 404 in one handler and 400 in another |
| Version owner | Who can change it and how consumers learn | generated client pinned to an old schema |
| Test | Which test crosses this boundary? | none; drift goes unnoticed |

## Worked example: an invoice status

| Boundary | Name/type | Missing/null | Allowed values | Test |
| --- | --- | --- | --- | --- |
| HTTP request | `status` string, optional filter | missing = all statuses | `open`, `paid`, `void` | handler test with each value and an unknown one |
| Domain | `InvoiceStatus` StrEnum | required | `OPEN`, `PAID`, `VOID` | domain transition tests |
| Storage | `status TEXT NOT NULL` | not allowed | enum `.value` strings | repository round-trip contract test |
| Provider webhook | `state` string | treated as protocol error | `settled`, `failed` | adapter mapping test: `settled` -> `PAID` |
| Generated client | `InvoiceStatus` union | optional | from OpenAPI schema | schema snapshot test |

The matrix immediately shows two decisions to make explicit: the webhook uses
a different vocabulary (`state`/`settled`) that needs a mapping table in the
adapter, and an unknown status must be rejected in the handler rather than
defaulted.

## Procedure

1. Name the concept and find its canonical definition (domain type, schema, or
   migration). If there are two, decide which wins before editing anything.
2. Search for every consumer: symbol references, string-based lookups
   (serializers, templates, configuration keys, SQL), fixtures, docs and
   generated code.
3. Fill one row per boundary. Leave a cell blank only when the property truly
   does not apply.
4. Mark each disagreement as *intentional* (documented mapping, compatibility
   alias with a removal condition) or *drift* (fix it).
5. Change the canonical definition first, then regenerate derived artifacts,
   then update hand-written consumers - in one change when possible.
6. Add or extend one test per boundary row that previously had none; prefer a
   test that crosses two boundaries (request to stored row) over two isolated
   ones.
7. For persisted or public values, write down the migration and rollback path
   before merging.

## Making the matrix executable

- Parametrize a test over the enum and assert every member round-trips through
  each serializer.
- Snapshot generated schemas and fail when the snapshot changes without a
  version bump.
- Assert defaults by reading them from the canonical place in the test, not by
  repeating the literal.
- Name-based checks ([`check_naming.py`](../assets/check_naming.py),
  [`check_class_file_naming.py`](../assets/check_class_file_naming.py)) catch
  spelling drift in file and class names only; they cannot prove two fields
  with the same name mean the same thing.

## Sources

- JSON Schema, [Understanding JSON Schema reference](https://json-schema.org/understanding-json-schema/reference)
- OpenAPI Initiative, [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- Python documentation, [enum](https://docs.python.org/3/library/enum.html)
  and [decimal](https://docs.python.org/3/library/decimal.html)
- pytest, [How to parametrize fixtures and test functions](https://docs.pytest.org/en/stable/how-to/parametrize.html)
