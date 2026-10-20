# Naming conventions across files, classes, modules and tests

Consistent names are a contract: tools import modules by file name, test
runners collect by prefix, serializers map field names, and humans search by
the words they expect. Choose one convention per *kind of name*, write it down
([naming policy worksheet](../assets/naming-policy.md.template)), and check it
mechanically where a tool can.

## A convention per kind of name

| Kind | Convention | Why | Example |
| --- | --- | --- | --- |
| Python module / package | `snake_case` | must be a valid identifier to import | `invoice_repository.py` |
| Python class | `CapWords` | PEP 8; distinguishes types from functions | `InvoiceRepository` |
| Function, method, variable | `snake_case` | PEP 8 | `list_open_invoices` |
| Constant | `UPPER_SNAKE` (`_UPPER` when private) | PEP 8 | `DEFAULT_TIMEOUT` |
| Type variable / alias | `CapWords`, short for type vars | PEP 8, PEP 695 | `type InvoiceId = str` |
| Test module | `test_<subject>.py` | default pytest discovery | `test_invoice_repository.py` |
| Test function | `test_<behavior>_<outcome>` | collected and readable in reports | `test_paid_invoice_cannot_be_voided` |
| Non-Python directory (docs, assets, config) | `kebab-case` | URL- and shell-friendly, no import rules | `getting-started/` |
| CLI flag | `--kebab-case` | POSIX/GNU style | `--max-public-classes` |
| Environment variable | `UPPER_SNAKE` with an app prefix | shells and containers | `APP_DATABASE` |
| JSON/YAML keys | one style per API, stated in the schema | wire compatibility | `invoice_id` or `invoiceId` |
| Branches, tags, artifacts | `kebab-case` | URL-safe | `fix-duplicate-charge` |

Language-neutral principles that apply beyond Python:

- **Name by meaning, not by type or layer**: `open_invoices`, not
  `invoice_list` or `invoice_dto_array`. Layer suffixes (`Repository`,
  `Gateway`, `Adapter`) are fine when they name a role.
- **One word per concept.** If the domain says "customer", do not mix in
  "client", "account" and "user" for the same thing. Record synonyms that are
  *not* the same concept.
- **Same concept, same spelling across boundaries**: a field called
  `payment_reference` in the domain should not become `paymentRef` in storage
  and `reference_id` in the API without a documented mapping.
- **Abbreviations**: use only well-known ones (`id`, `url`, `http`), spell
  them consistently, and in `CapWords` treat them as words (`HttpClient`) or as
  all-caps (`HTTPClient`) - pick one per codebase.
- **Booleans** read as predicates: `is_payable`, `has_reference`, `allow_extra`.

## Names that tools depend on

- A Python file with a hyphen, a leading digit or a keyword name cannot be
  imported normally. A module named like a standard-library module
  (`logging.py`, `email.py`) in a directory on `sys.path` shadows the real one.
- pytest collects `test_*.py` or `*_test.py`, functions prefixed `test`, and
  classes prefixed `Test` without an `__init__`. Two test modules with the same
  basename in directories without `__init__.py` collide under the default
  import mode (see the test-hygiene checker in the test-first skill).
- Case-insensitive file systems treat `Invoice.py` and `invoice.py` as one file;
  never rely on case alone to distinguish names.

## Checking file and directory names

[`check_naming.py`](../assets/check_naming.py) scans a tree without reading
file contents:

```text
python check_naming.py .                               # Python names only
python check_naming.py . --kebab-root docs --kebab-root assets
python check_naming.py . --packages-only --forbid-stdlib-shadow
python check_naming.py . --ignore "legacy/*" --exclude generated
python check_naming.py --self-test
```

- Every `.py` file stem must be `snake_case` (dunder modules exempt) and not a
  keyword.
- Directories containing Python files must be `snake_case`
  (`--packages-only` narrows this to directories with `__init__.py`).
- Directories below each `--kebab-root` that contain no Python files must be
  `kebab-case`; use `--kebab-root .` for the whole tree.
- `--forbid-stdlib-shadow` reports modules outside any package that reuse a
  standard-library name.
- Dot-directories are skipped by name; build, cache and virtual-environment
  folders are excluded by default.

## Rolling out a convention in an existing codebase

1. Run the checker and count findings per directory.
2. Decide per directory: rename now, exempt with a dated `--ignore`, or change
   the convention. Renames of public modules need re-export shims or a
   deprecation window.
3. Rename with a refactoring tool (or `git mv` plus import updates), one
   package per change, and run the full test suite.
4. Add the checker to the gate only after the baseline is clean, so new code
   cannot regress.

## Sources

- [PEP 8: Style Guide for Python Code, naming conventions](https://peps.python.org/pep-0008/#naming-conventions)
- Python tutorial, [Modules and packages](https://docs.python.org/3/tutorial/modules.html)
- Python documentation, [sys.stdlib_module_names](https://docs.python.org/3/library/sys.html#sys.stdlib_module_names)
  and [keyword](https://docs.python.org/3/library/keyword.html)
- pytest, [Conventions for Python test discovery](https://docs.pytest.org/en/stable/explanation/goodpractices.html#conventions-for-python-test-discovery)
- [PEP 695: Type Parameter Syntax](https://peps.python.org/pep-0695/)
