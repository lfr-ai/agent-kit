# Module layout, centralization, public names and exports

## Choose cohesion before a class count

When `invoice_repository.py` defines `InvoiceRepository`, readers find code by
name, diffs touch the file you expect, and import statements document the
dependency precisely. It also keeps modules small enough that a reviewer can
hold one in mind. Class/file alignment is a project navigation convention, not
a Python requirement. A cohesive group of functions, records or exceptions may
be clearer together. Do not split it merely to obtain one class per file.

## Centralize at the narrowest semantic owner

| Situation | Prefer | Avoid |
| --- | --- | --- |
| One helper serves one module | A private helper beside its caller | A repository-wide `utils` export with no other consumer |
| Several callers share the same rule and change together | One named definition owned by that rule's domain | Independent copies of the same policy |
| Similar syntax serves different business concepts | Separate, explicitly named implementations | Merging unrelated concepts because the code looks alike |
| A contract crosses a boundary | One owned contract plus explicit adapters and mappings | Forcing domain, transport and persistence into one universal model |
| Framework settings or process resources need one lifetime | Configuration and wiring at the composition boundary | Import-time clients, mutable global registries or service locators |
| Generated artifacts repeat source information | Regeneration from the canonical owner | Independently maintained copies or hashes refreshed to conceal drift |

Determine the owner from meaning, dependency direction and change ownership,
not the number of occurrences alone. Shared code belongs at the lowest
appropriate dependency boundary; do not invert layer imports just to reuse it.
Public constants, enums and schemas can be centralized when they represent one
contract. Identically spelled statuses, defaults or identifiers from separate
domains may intentionally remain different.

Move a definition only when its callers can depend on the new owner without
cycles or unnecessary coupling. Measure the trade-off: fewer policy copies
should not require many more files, parameters, imports or runtime lookups.
Prefer a named domain module over growing `common`, `helpers` or `constants`
into a collection of unrelated concerns.

## Module versus subfolder decisions

| Choice | Evidence that justifies it |
| --- | --- |
| Keep code in one module | One cohesive responsibility, shared lifecycle and understandable navigation |
| Split into modules | Distinct responsibilities, public contracts or change ownership can be separated cleanly |
| Introduce a subpackage | Several related modules form a real boundary with a useful public API |
| Keep the layout flat | A small CLI, library or feature has no meaningful internal grouping yet |
| Use feature-oriented or layered grouping | The existing architecture and dependency direction justify that grouping |

Do not create empty future folders, a layer per file, or a deep hierarchy solely
because a template has one. Use names such as `billing` or `serialization` when
they describe actual ownership; use role folders only when they group a real
set of collaborators. A move should make "where is this implemented/tested?"
easier to answer, not merely reduce a file's line count.

For Python, distinguish a module, regular package and intentional namespace
package. Keep `__init__.py` and re-exports deliberate; adding a folder must not
accidentally change imports or package discovery. A `src` distribution layout
addresses packaging isolation, not how deeply every feature must be nested.
Follow the project's casing rules and tool-required filenames. Avoid standard
library shadowing, case-only distinctions and renames that break public imports.

## If the project adopts a class-per-module convention

The existing checker supports the following explicit project convention.
Apply it to agreed scopes and a counted baseline, not as an automatic migration
rule for every repository. For each module that is not exempt:

1. Count the public top-level classes, ignoring names that start with `_` and
   classes that are support types by convention (names ending in `Error`,
   `Exception` or `Warning`; optionally subclasses of configured bases).
2. One counted class should correspond to the module name:
   `snake_case(ClassName) == module_stem` (exact), or - when adapters carry a
   technology prefix - the names extend each other by whole words
   (`SqliteInvoiceRepository` in `invoice_repository.py`, affix mode).
3. Review any further counted class against the declared maximum and cohesion.
   Split responsibilities when that improves the design, or record a justified
   grouping exemption. Make a helper private only when it is genuinely internal;
   never hide a public type merely to silence the checker.

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
module. Keep any required public type public and follow the project's declared
grouping policy. A different `--max-public-classes` or an exemption needs an
ownership/cohesion justification, not merely a desire to make a check pass.

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

## Verify a centralization or layout change

- Identify the canonical owner and every symbol and string-based caller.
- Update imports, entry points, registries, configuration, resource paths,
  documentation and fixtures together; regenerate owned derivatives.
- Preserve public names and persisted/wire values, or provide an approved,
  tested migration. Keep compatibility aliases only for known consumers.
- Run the project's naming, type, architecture and affected behavior checks.
  Naming agreement alone cannot prove that two concepts mean the same thing.
- For distribution changes, prove regular installation and resource loading
  away from the source tree, not just imports from an editable checkout.

## Sources

- [PEP 8: Style Guide for Python Code, public and internal interfaces](https://peps.python.org/pep-0008/#public-and-internal-interfaces)
- Python tutorial, [Importing * from a package](https://docs.python.org/3/tutorial/modules.html#importing-from-a-package)
- Python typing specification, [Import conventions for stubs and re-exports](https://typing.python.org/en/latest/spec/distributing.html#import-conventions)
- Python documentation, [warnings](https://docs.python.org/3/library/warnings.html)
- [Python modules and packages](https://docs.python.org/3.13/tutorial/modules.html)
- [PyPA: src layout versus flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
- [Google engineering review: design, complexity and naming](https://google.github.io/eng-practices/review/reviewer/looking-for.html)
