# Method and function ordering

Order code so it reads top-down like a newspaper: the high-level operation
first, then the steps it delegates to. This is often called the stepdown rule.

## Class layout

1. Class docstring and class-level constants.
2. Field declarations (dataclasses) or `__slots__`.
3. Construction: `__init__`, `__post_init__`, then alternative constructors
   (`@classmethod` factories).
4. Public properties.
5. Public methods, most important use case first.
6. Comparison and representation dunders (`__eq__`, `__hash__`, `__repr__`)
   when hand-written.
7. Private helpers, each placed below the first method that calls it.

## Module layout

1. Module docstring.
2. Imports (standard library, third party, first party; Ruff's isort orders them).
3. Module constants and type aliases.
4. Public classes and functions in the order a reader needs them.
5. Private helpers below their caller.
6. `main()` and the `if __name__ == "__main__":` guard last.

## Stepdown rule for private helpers

A private helper (`_name`) with exactly one caller in the same scope lives
directly below that caller, or below the caller's other helpers. Helpers shared
by several callers live below the last caller.

```python
class ReportService:
    def build(self, *, period: DateRange) -> Report:
        rows = self._collect(period)
        return Report(rows=self._summarize(rows))

    def _collect(self, period: DateRange) -> list[Row]: ...

    def _summarize(self, rows: list[Row]) -> list[SummaryRow]: ...
```

A reader encounters `build`, learns the two steps, and finds both immediately
afterwards in call order.

## Automated check

[check_method_ordering.py](../assets/check_method_ordering.py) reports private
helpers that are defined before their sole caller.

```text
python check_method_ordering.py src/
python check_method_ordering.py src/ --scope class
python check_method_ordering.py src/ --order before --ignore "^_setup"
```

Options:

- `--order after|before` chooses stepdown (default) or the inverse convention.
- `--scope module|class|all` restricts which scopes are checked.
- `--ignore REGEX` skips helper names matching a pattern (repeatable).
- `--exclude NAME` skips directories by name (repeatable).

Only helpers with exactly one referencing function are judged. Helpers used by
several functions, or only at module import time, are left alone because no
single position is obviously correct.

## Exceptions

- Overloads and properties with setters stay adjacent to each other.
- A framework may require a declaration order (for example ORM column order or
  test fixture discovery); framework order wins.
- Do not reorder a large file in the same change as a behavior fix. Make the
  move in a separate, behavior-preserving change so review stays readable.

## Sources

- [PEP 8 - Style guide for Python code](https://peps.python.org/pep-0008/)
- [Python data model: special method names](https://docs.python.org/3/reference/datamodel.html#special-method-names)
- [Ruff isort rules](https://docs.astral.sh/ruff/rules/#isort-i)
