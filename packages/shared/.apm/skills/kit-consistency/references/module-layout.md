# Module layout: one public class per module, private names and exports

## Why one public class per module

When `invoice_repository.py` defines `InvoiceRepository`, readers find code by
name, diffs touch the file you expect, and import statements document the
dependency precisely. It also keeps modules small enough that a reviewer can
hold one in mind. The rule is a navigation convention, not a law of design:
apply it where classes are the main unit and exempt modules whose purpose is
grouping.

## The rule, precisely

For each module that is not exempt:

1. Count the public top-level classes, ignoring names that start with `_` and
   classes that are support types by convention (names ending in `Error`,
   `Exception` or `Warning`; optionally subclasses of configured bases).
2. One counted class should correspond to the module name:
   `snake_case(ClassName) == module_stem` (exact), or - when adapters carry a
   technology prefix - the names extend each other by whole words
   (`SqliteInvoiceRepository` in `invoice_repository.py`, affix mode).
3. Any further counted class beyond the allowed maximum either moves to its
   own module or becomes private.

Typical exemptions:

| Module | Why it groups |
| --- | --- |
| `__init__.py` | package API and re-exports |
| `test_*.py`, `conftest.py` | test classes and fixtures |
| `exceptions.py`, `errors.py` | an exception hierarchy reads best together |
| `models.py`, `schemas.py`, `types.py` | small value types or wire schemas of one aggregate |
| `constants.py`, `enums.py` | closed sets of names |
| generated code | owned by the generator |

Small cohesive helpers that only exist to serve the main class (a frozen
command dataclass next to its use case, a result type) are fine in the same
module; either make them private, count them under a raised
`--max-public-classes`, or document the module as exempt.

## Checking it

[`check_class_file_naming.py`](../assets/check_class_file_naming.py):

```text
python check_class_file_naming.py src
python check_class_file_naming.py src --match affix --exempt "*/models.py"
python check_class_file_naming.py src --max-public-classes 2 --ignore-base Protocol
python check_class_file_naming.py src --no-default-exempt --exempt "__init__.py"
python check_class_file_naming.py --self-test
```

The name conversion treats acronyms as words: `HTTPClient` maps to
`http_client`, `InvoicePDFExport` to `invoice_pdf_export`. If a class name and
module disagree only because of an acronym style, rename one of them rather
than adding an exemption.

## Private names and what a module exports

- A leading underscore (`_helper`, `_Row`, `_TIMEOUT`) means "not part of this
  module's API". Tests may reach private helpers when pinning an internal
  algorithm, but other production modules should not.
- `__all__` lists the public names a module intends to export. Define it in
  package `__init__.py` files that re-export, and in modules where a wildcard
  import or documentation tool would otherwise pick up imported names.
- Re-export deliberately: `from app.domain.invoice import Invoice as Invoice`
  or an `__all__` entry tells type checkers and linters the re-export is
  intended. Do not let callers depend on names that merely happen to be
  imported into a module.
- Keep one import path per public name. If both `app.domain` and
  `app.domain.invoice` export `Invoice`, pick the canonical one for docs and
  tests, and treat the other as a compatibility alias with a removal plan.
- Moving a public class is a breaking change for consumers. Leave a shim that
  re-exports and warns (`warnings.warn(..., DeprecationWarning, stacklevel=2)`)
  for one release when the module is part of a published API.

## Tests mirror the source layout

- `src/app/domain/invoice.py` -> `tests/unit/domain/test_invoice.py`.
- One test module per source module keeps "where is this tested?" answerable
  by path; split large test modules by behavior, not by test type.
- Shared fixtures live in the nearest `conftest.py` that covers every user,
  factories in a `factories.py` module, fakes in `fakes.py`.

## Sources

- [PEP 8: Style Guide for Python Code, public and internal interfaces](https://peps.python.org/pep-0008/#public-and-internal-interfaces)
- Python tutorial, [Importing * from a package](https://docs.python.org/3/tutorial/modules.html#importing-from-a-package)
- Python typing specification, [Import conventions for stubs and re-exports](https://typing.python.org/en/latest/spec/distributing.html#import-conventions)
- Python documentation, [warnings](https://docs.python.org/3/library/warnings.html)
