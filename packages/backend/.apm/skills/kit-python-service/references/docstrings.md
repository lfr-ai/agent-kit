# Docstring patterns

Docstrings explain behavior that the signature cannot: intent, constraints, side
effects, and failures. Prefer the simplest form: a one-line docstring that
states the whole contract, including what a return value means. Comments are
single lines that say why, never what the next line does.

## Toolkit defaults

Google style with triple double quotes. The summary is one imperative or
descriptive sentence (consistent within a file) that fits on one line and ends
with a period; a blank line separates it from any details. Inline code uses
paired double-backtick literals (reStructuredText); Markdown files keep CommonMark
single backticks.

PEP 257 reserves one-line docstrings for "really obvious cases"; Google §3.8.3
lets sections be omitted when the name and signature are informative enough for
a one-line docstring. Choose by caller-relevant complexity, not parameter count:

| One line when | Multi-line when |
| --- | --- |
| The name, signature, and summary explain the contract; sections would only restate them. This includes public wrappers, delegates with several self-evident parameters, and structured returns whose shape fits in the summary. | A structured return needs more than one line to describe (then `Returns:` is required, see `docstring-returns`), or constraints, effects, failures, yields, or examples need more explanation. Prose is sufficient when sections add no clarity. |
| A short summary can state the notable input and failure behavior without losing meaning, including an explicit exception-message constructor. | Initializer parameters with units, ranges, or interactions that need explanation; document these in prose or `Args:` on `__init__`. |

```python
def _context(actions: CliActions) -> int:
    """Read bounded stdin JSON and emit advisory context; ``1`` on check failure."""


def emit(report: CheckReport, stream: TextIO) -> None:
    """Write ``report`` findings to ``stream``, one per line."""


def _report_dict(report: CheckReport) -> dict[str, object]:
    """Return the JSON report: ``valid``, ``version``, ``findings`` and ``profiles``."""


def scale(value: float, factor: float) -> float:
    """Multiply a measurement by a unit-conversion factor.

    Args:
        value (float): Measurement in source units.
        factor (float): Target units per source unit; must be positive.
    """
```

When an `Args:` section exists, it lists every parameter in signature order as
`name (type): meaning`, with `type` equal to the annotation. Types are
machine-checked, so the repetition cannot drift. Keep real input, error, and
constraint contracts even when shortening a docstring. Do not remove meaningful
sections merely because the callable takes one parameter.

## Enforced rules

Run `python check_python.py --docstrings <paths>` or select rules with `--only`;
the rules are opt-in in the checker and default-on in this repository's gate.

| Finding code | Fires when |
| --- | --- |
| `docstring-args` | Initializer prose does not name every parameter in double backticks and lacks `Args:`, or any `Args:` section does not list every parameter in signature order (excluding `self`/`cls`). |
| `docstring-args-type` | An `Args:` entry omits `(type)` or its type differs from the unparsed annotation (whitespace and quotes are normalised; `X \| None` is compared literally). |
| `docstring-returns` | A multi-line docstring's return annotation is a tuple of two or more elements, a `dict`/`Mapping`, a nested generic, a `Callable`, or a union of two or more non-`None` types, and `Returns:` is missing or empty. A one-line summary that states the shape passes. Generators and `TypeGuard`/`TypeIs` predicates are exempt. |
| `docstring-returns-none` | `Returns:` appears on a function annotated `-> None`. |

Exempt: test modules, dunder methods other than `__init__`, `@overload` stubs,
properties, and `@override` methods. Missing docstrings outside parameterized
initializers are left to the project's documentation linter. The checker validates
section structure and annotated types, not whether prose is meaningful. Concision
and completeness require review; there is no signature-based one-line rule.

Ruff selects the pydoclint preview rules by exact code: `DOC102` (documented
parameter not in the signature), `DOC202` (`Returns:` without a return),
`DOC402`/`DOC403` (missing or extraneous `Yields:`), and `DOC501` (raised
exception missing from `Raises:`). `DOC201` is off because one-line docstrings
state the return in the summary; `DOC502` is off because `Raises:` also lists
failures propagated from callees.

## Module docstrings

State what the module owns and what it deliberately does not own.

```python
"""Invoice issuing use cases.

Owns numbering and issue-date rules. Persistence and PDF rendering are adapters
injected through the ports in ``invoicing.ports``.
"""
```

## Function docstrings

One-line, self-evident parameters and an obvious return:

```python
def normalise_name(name: str) -> str:
    """Return ``name`` trimmed and lower-cased."""
    return name.strip().lower()
```

Several parameters, a structured return, and handled failures:

```python
def allocate(
    order: Order, *, warehouse: Warehouse, limit: int | None = None
) -> dict[str, int]:
    """Reserve stock for every line of an order.

    Lines are reserved atomically: either all lines are reserved or none are.

    Args:
        order (Order): Confirmed order; draft orders are rejected.
        warehouse (Warehouse): Stock source consulted for availability.
        limit (int | None): Maximum units reserved per line; ``None`` means no cap.

    Returns:
        Reserved units keyed by order-line identifier, in line order; empty for
        an order without lines.

    Raises:
        OrderNotConfirmedError: If ``order`` is still a draft.
        OutOfStockError: If any line cannot be fully reserved.
    """
```

Variadic parameters are documented with their stars and the element annotation:

```python
def log_all(prefix: str, *args: object, **kwargs: str) -> None:
    """Write each value to the log under ``prefix``.

    Args:
        prefix (str): Text placed before every entry.
        *args (object): Values rendered with ``str``.
        **kwargs (str): Extra fields appended as ``key=value``.
    """
```

Generators use `Yields:` instead of `Returns:`:

```python
def chunks(items: list[int], size: int) -> Iterator[list[int]]:
    """Split ``items`` into consecutive batches.

    Args:
        items (list[int]): Values to split.
        size (int): Maximum batch length; must be positive.

    Yields:
        Consecutive slices of ``items`` in order; the last may be shorter.
    """
    for start in range(0, len(items), size):
        yield items[start : start + size]
```

Guidance:

- `Args:` documents meaning, units, and accepted ranges; the type is checked.
- `Returns:` describes the value's structure and meaning. For structured values,
  name keys, tuple positions, units, ordering, and empty cases. Prefer a
  `TypedDict` or named record to a dictionary with an unrelated union of values.
- `Raises:` lists exceptions that callers are expected to handle. Do not list
  every exception a dependency might raise.
- Generators use `Yields:` for each yielded value, including order and the
  no-results case when relevant.

## Class docstrings

Describe responsibility and invariants. Document public attributes of records in
`Attributes:`. Document initializer arguments on `__init__`, even when there is
only one: concise prose names each parameter in double backticks and states its
meaning, or an `Args:` section adds units, constraints, and interactions. A fixed
exception-message constructor need not add a section merely to repeat its type:

```python
class ContractError(ValueError):
    def __init__(self, issue: Issue) -> None:
        """Retain ``issue`` and use its fixed diagnostic as the message."""
        self.issue = issue
        super().__init__(issue.value)
```

```python
@dataclass(frozen=True, kw_only=True, slots=True)
class DateRange:
    """Closed interval of calendar dates.

    Attributes:
        start (date): First day included in the range.
        end (date): Last day included in the range; never before ``start``.
    """

    start: date
    end: date
```

## Properties

Document a property like an attribute, with a noun phrase, not a verb. Properties
are exempt from `Args:` and `Returns:`.

```python
@property
def total(self) -> Decimal:
    """Total including tax."""
    return self.net + self.tax
```

## Overridden methods

An override that keeps the parent's contract (`@override`) is exempt. Use a
one-line docstring that names the difference, or none if the project allows
inheriting docs. Do not copy the parent's docstring. An override that changes the
contract documents it like any other callable.

## Tests

Test modules are exempt from the checker. Test docstrings state the behavior
under test in one sentence: `"""A draft order cannot be allocated."""`. The test
name and the docstring together form the specification.

## Anti-patterns

| Anti-pattern | Fix |
| --- | --- |
| `"""Get order."""` on `get_order` | Say what is notable or remove the noise. |
| `Args:` missing a type, or a type that differs from the annotation | Write `name (type): meaning` with the annotation verbatim; change both together. |
| `Args:`/`Returns:` that only repeat a self-evident signature | Use concise prose that keeps notable inputs, constraints, effects, and failures. |
| `Returns:` that only repeats the type | Describe shape, keys, units, ordering, and empty cases. |
| `Raises: Exception` | Name the specific, handled exceptions. |
| Implementation narration | Describe the contract; comment tricky lines instead. |
| Single-backtick or single-quoted code | Use paired double-backtick literals. |
| Docstring that disagrees with code | Pin behavior first; report defects separately from a behavior-preserving cleanup. |

## Consumer overrides

Google and PEP 257 leave inline markup open. Sphinx and reStructuredText define
double backticks as inline literals; the toolkit adopts that syntax for
docstrings while keeping Markdown file syntax unchanged.

## Primary sources

- [Google Python Style Guide: comments and docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
- [Google Python Style Guide §3.8.3: functions and methods](https://google.github.io/styleguide/pyguide.html#383-functions-and-methods)
- [PEP 257 - Docstring conventions](https://peps.python.org/pep-0257/)
- [PEP 257: one-line docstrings](https://peps.python.org/pep-0257/#one-line-docstrings)
- [Ruff pydocstyle rules](https://docs.astral.sh/ruff/rules/#pydocstyle-d)
- [Ruff pydoclint rules (DOC)](https://docs.astral.sh/ruff/rules/#pydoclint-doc)
- [pydoclint](https://jsh9.github.io/pydoclint/)
- [Sphinx Napoleon: Google style example](https://www.sphinx-doc.org/en/master/usage/extensions/example_google.html)
- [Sphinx reStructuredText Primer: inline markup](https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html#inline-markup)
- [Docutils Quick reStructuredText reference](https://docutils.sourceforge.io/docs/user/rst/quickref.html#inline-markup)
