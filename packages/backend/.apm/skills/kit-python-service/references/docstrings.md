# Docstring patterns

Docstrings explain behavior that the signature cannot: intent, constraints, side
effects, and failures. They do not restate annotated types.

## Toolkit defaults

- Triple double quotes for every docstring, including one-liners.
- Google style sections (`Args:`, `Returns:`, `Yields:`, `Raises:`,
  `Attributes:`, `Example:`) only when they add caller-relevant information.
- Inline code in Python docstrings uses paired double-backtick literals, the
  reStructuredText convention. Do not use single-quoted code names or single
  backticks. Markdown documents still use standard CommonMark single backticks.
  The bundled [checker](../assets/check_python.py) enforces this rule.
- Summary line: one sentence, ends with a period, fits on one line, written in a
  consistent mood within the file (imperative "Return the..." or descriptive
  "Returns the...").
- A blank line separates the summary from the details.

## Module docstrings

State what the module owns and what it deliberately does not own.

```python
"""Invoice issuing use cases.

Owns numbering and issue-date rules. Persistence and PDF rendering are adapters
injected through the ports in ``invoicing.ports``.
"""
```

## Function docstrings

```python
def allocate(order: Order, *, warehouse: Warehouse) -> Allocation:
    """Reserve stock for every line of an order.

    Lines are reserved atomically: either all lines are reserved or none are.

    Args:
        order: Confirmed order; draft orders are rejected.
        warehouse: Stock source consulted for availability.

    Returns:
        Allocation describing the reserved quantity per line.

    Raises:
        OrderNotConfirmedError: If ``order`` is still a draft.
        OutOfStockError: If any line cannot be fully reserved.
    """
```

Guidance:

- `Args:` documents meaning, units, and accepted ranges, not the type.
- `Returns:` describes the value's meaning. Omit it for `-> None`.
- `Raises:` lists exceptions that callers are expected to handle. Do not list
  every exception a dependency might raise.
- Generators use `Yields:` instead of `Returns:`.

## Class docstrings

Describe responsibility and invariants. Document public attributes of records in
`Attributes:`; document initializer arguments on `__init__`.

```python
@dataclass(frozen=True, kw_only=True, slots=True)
class DateRange:
    """Closed interval of calendar dates.

    Attributes:
        start: First day included in the range.
        end: Last day included in the range; never before ``start``.
    """

    start: date
    end: date
```

## Properties

Document a property like an attribute, with a noun phrase: `"""Total including
tax."""`, not `"""Returns the total."""`.

## Overridden methods

An override that keeps the parent's contract can use a one-line docstring that
names the difference, or none if the project allows inheriting docs. Do not copy
the parent's docstring.

## Tests

Test docstrings state the behavior under test in one sentence:
`"""A draft order cannot be allocated."""`. The test name and the docstring
together form the specification.

## Anti-patterns

| Anti-pattern | Fix |
| --- | --- |
| `"""Get order."""` on `get_order` | Say what is notable or remove the noise. |
| Types repeated in `Args:` | Rely on annotations. |
| `Raises: Exception` | Name the specific, handled exceptions. |
| Implementation narration | Describe the contract; comment tricky lines instead. |
| Single-backtick or single-quoted code | Use paired double-backtick literals. |
| Docstring that disagrees with code | Fix whichever is wrong in the same change. |

## Consumer overrides

Google and PEP 257 leave inline markup open. Sphinx and reStructuredText define
double backticks as inline literals; the toolkit adopts that syntax for
docstrings while keeping Markdown file syntax unchanged.

## Sources

- [Google Python Style Guide: comments and docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
- [PEP 257 - Docstring conventions](https://peps.python.org/pep-0257/)
- [Ruff pydocstyle rules](https://docs.astral.sh/ruff/rules/#pydocstyle-d)
- [Sphinx Napoleon: Google style example](https://www.sphinx-doc.org/en/master/usage/extensions/example_google.html)
- [Sphinx reStructuredText Primer: inline markup](https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html#inline-markup)
- [Docutils Quick reStructuredText reference](https://docutils.sourceforge.io/docs/user/rst/quickref.html#inline-markup)
