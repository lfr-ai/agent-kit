# Docstring patterns

Docstrings explain behavior that the signature cannot: intent, constraints, side
effects, and failures. Length follows the contract, not visibility: one line when
the name and signature already tell the story, sections only for what they add.
Comments are single lines that say why, never what the next line does.

## Toolkit defaults

Google style with triple double quotes. The summary is one imperative or
descriptive sentence (consistent within a file) that fits on one line and ends
with a period; a blank line separates it from any details. Inline code uses
paired double-backtick literals (reStructuredText); Markdown files keep CommonMark
single backticks.

PEP 257 reserves one-line docstrings for "really obvious cases"; Google §3.8.3
lets sections be omitted when the name and signature are informative enough, and
limits `Raises:` to exceptions relevant to the interface. A callable with at most
one input is that case: the input's meaning is its name and annotation, so
sections only repeat the signature. Google also allows annotated types to be
omitted from sections. Here, sections are optional for two or more inputs;
supplied sections explain meaning, and type repetition is optional. If a section
does repeat a type, the checker verifies it against the annotation.

| One line when | Multi-line when |
| --- | --- |
| The callable takes at most one input (excluding `self`/`cls`), whatever its body size. Fold the result and any raised error into the summary; a short prose paragraph may follow for genuinely complex behavior, never sections. | Two or more inputs interact, carry units or ranges, or the result has structure (keys, positions, ordering, empty cases). Sections stay optional; do not discard meaningful details just to shorten docs. |
| An initializer's prose explains its arguments, even for an exception-message constructor. | `Args:` clarifies initializer (`__init__`, `__post_init__`) units, ranges or interactions at any arity. Supplied sections must be complete; optional types must match. |

```python
def _context(actions: CLIActions) -> int:
    """Read bounded stdin JSON and emit advisory context; ``1`` on check failure."""


def mapping(value: object) -> dict[str, object]:
    """Return ``value`` as a string-keyed mapping; raise ``ValueError`` otherwise."""


def emit(report: CheckReport, stream: TextIO) -> None:
    """Write each finding of ``report`` to ``stream`` on its own line."""


def _report_dict(report: CheckReport) -> dict[str, object]:
    """Return the JSON report: ``valid``, ``version``, ``findings`` and ``profiles``."""


def scale(value: float, factor: float) -> float:
    """Multiply a measurement by a unit-conversion factor.

    Args:
        value: Measurement in source units.
        factor: Target units per source unit; must be positive.

    Returns:
        Measurement in target units.
    """
```

When supplied, `Args:` lists every parameter except `self`/`cls`, in signature
order as `name: meaning`. An optional `(type)` may be included and is checked
against the annotation. Keep real input, error, and constraint contracts even
when shortening a docstring.

## Raises scope

`Raises:` documents what the callable itself raises, matching pydoclint
`DOC501`/`DOC502` semantics:

- a direct `raise SomeError(...)` in the body;
- a translation `raise BoundaryError(...) from exc`, which documents the new
  type, not the original;
- a re-raise of a caught type (`except SomeError: ...; raise`).

Never list failures that only propagate from callees (`OSError` from `open`,
`SyntaxError` from `ast.parse`, a domain error raised inside a helper). When a
propagated failure is essential to callers, say so in the summary or in the
parameter meaning instead, or raise it in the public method itself. Interface
contracts are exempt: `Protocol` members, `@abstractmethod`s and stubs whose body
is only `...`, `pass` or `raise NotImplementedError` document what implementations
raise, in prose when the member takes at most one input.

## Enforced rules

Run `python check_python.py --docstrings <paths>` or select rules with `--only`;
the rules are opt-in in the checker and default-on in this repository's gate.

| Finding code | Fires when |
| --- | --- |
| `docstring-missing` | A public callable has no docstring. |
| `docstring-args` | Initializer parameters are unexplained in prose and lack `Args:`, or a supplied section is empty, malformed, missing a meaning, or differs from signature order (excluding `self`/`cls`). |
| `docstring-args-type` | An optional `(type)` in `Args:` differs from the annotation (whitespace and quotes are normalised; `X \| None` is compared literally). |
| `docstring-returns` | A supplied `Returns:` section is empty, undescribed, or contains an incorrect optional type. Omitted sections pass for all result shapes, including `TypeGuard`/`TypeIs`. |
| `docstring-returns-none` | `Returns:` appears on a procedure, generator or `Never`/`NoReturn` callable. |
| `docstring-property` | A `@property` or `@cached_property` getter has a `Returns:` section; document it like an attribute (`"""Whether the catalog has no findings."""`). |
| `docstring-yields` | Supplied `Yields:` is empty, undescribed, contains an incorrect optional type, or belongs to a non-generator. Its type is the yielded element, not the iterator wrapper. |
| `docstring-raises` | A supplied section is empty/undescribed or omits a statically known escaping error not mentioned in explanatory prose. Omitting the section is allowed; failure semantics remain review-owned. |
| `docstring-raises-extra` | `Raises:` names a type the body never raises directly, translates or re-raises (a documented base of a raised type is accepted). Skipped for interface contracts and for bodies that raise dynamic types such as factories or variables. |
| `docstring-one-line` | A callable with at most one input (excluding `self`/`cls`; counting positional, `*args`, keyword-only and `**kwargs`) carries `Args:`, `Returns:`, `Yields:` or `Raises:`, whatever its body size. Initializers, properties, `@overload` stubs and test functions are exempt; overrides and other dunders are not. |
| `docstring-class-sections` | A class docstring has `Args:`, `Returns:`, `Yields:` or `Raises:`; use `Attributes:` for fields and document arguments and failures on `__init__`/`__post_init__`. |

Exempt: test modules/functions, standard dunders other than `__init__`,
`@overload` stubs and explicit `@override` methods retaining a documented
interface; `docstring-one-line` still applies to those dunders and overrides.
Private/nested helpers may omit docstrings; all callables may omit sections.
Supplied sections are validated.
Initializers document parameters even on private classes. Public properties
need docstrings written like attributes (Google style): a one-line noun phrase
or "Whether ..." clause, never a `Returns:` section. No empty sections and no
`Returns: None` boilerplate. References/example mentions alone do not explain
initializer arguments.

The AST check does not execute source. It sees direct explicit raises,
translations and typed handler re-raises, excludes locally caught errors and
nested callable bodies, and parses directly imported local class definitions to
recognize catches of their base exceptions. Built-in exception ancestry is known.
Unavailable source, transitive imports and ambiguous names still require review;
this is not a full type checker or interprocedural analysis. The one-line rule
counts inputs only; reviewers still shorten boilerplate on multi-input callables.

Ruff selects `DOC102` (unknown documented parameter), `DOC202` (`Returns:`
without a return) and `DOC403` (extraneous `Yields:`); `D417` checks supplied
`Args:` for completeness. `DOC201` and `DOC402` are deliberately not selected:
they require sections where this policy accepts summaries. `DOC501` and `DOC502`
are preview rules that match names only; they cannot distinguish exception
factories from classes, resolve local subclasses or exempt interface contracts,
so `docstring-raises` and `docstring-raises-extra` own both directions. Do not
fabricate `Raises: _invalid` for a factory. These are policy-level choices, not
per-file suppressions.

## Module docstrings

State what the module owns and what it deliberately does not own.

```python
"""Invoice issuing use cases.

Owns numbering and issue-date rules. Persistence and PDF rendering are adapters
injected through the ports in ``invoicing.ports``.
"""
```

## Function docstrings

Simple complete contracts need no signature repetition:

```python
def normalise_name(name: str) -> str:
    """Return ``name`` trimmed and lower-cased."""
    return name.strip().lower()


def is_int(value: object) -> TypeGuard[int]:
    """Return whether ``value`` is an integer."""
    return isinstance(value, int)
```

Several parameters, a structured return, and failures the body raises:

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
        dict[str, int]: Reserved units keyed by order-line identifier, in line order; empty for
        an order without lines.

    Raises:
        OrderNotConfirmedError: If ``order`` is still a draft.
        OutOfStockError: If any line cannot be fully reserved.
    """
    if order.is_draft:
        raise OrderNotConfirmedError(order.order_id)
    reserved = warehouse.try_reserve(order.lines, limit=limit)
    if reserved is None:
        raise OutOfStockError(order.order_id)
    return reserved
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

When a generator benefits from a section, use `Yields:` instead of `Returns:`:

```python
def chunks(items: list[int], size: int) -> Iterator[list[int]]:
    """Split ``items`` into consecutive batches.

    Args:
        items (list[int]): Values to split.
        size (int): Maximum batch length; must be positive.

    Yields:
        list[int]: Consecutive slices of ``items`` in order; the last may be shorter.

    Raises:
        ValueError: The size is not positive.
    """
    if size <= 0:
        message = "size must be positive"
        raise ValueError(message)
    for start in range(0, len(items), size):
        yield items[start : start + size]
```

Guidance:

- `Args:` documents meaning, units, and accepted ranges; an optional type is checked.
- `Returns:` describes the value's structure and meaning. For structured values,
  name keys, tuple positions, units, ordering, and empty cases. Prefer a
  `TypedDict` or named record to a dictionary with an unrelated union of values.
- `Raises:` lists exceptions the body raises, translates or re-raises (see
  [Raises scope](#raises-scope)); never every exception a dependency might raise.
- Generators use `Yields:` for each yielded value, including order and the
  no-results case when relevant.

## Class docstrings

Describe responsibility and invariants. Document public attributes of records in
`Attributes:` when helpful. Class docstrings never carry `Args:`, `Returns:`,
`Yields:` or `Raises:`: explain initializer arguments on `__init__`, even when
there is only one, and validation failures on the `__init__` or `__post_init__`
that raises them. Concise prose can fully explain a fixed error constructor:

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

Google documents properties like attributes: a one-line noun phrase or
"Whether ..." clause, never a `Returns:` section.

```python
@property
def total(self) -> Decimal:
    """Net amount plus tax in the invoice currency."""
    return self.net + self.tax
```

## Overridden methods

An override that keeps the parent's contract (`@override`) is exempt from
contract checks, not from `docstring-one-line`. Use a one-line docstring that
names the difference, or none if the project allows inheriting docs. Do not copy
the parent's docstring. An override that changes the contract documents it like
any other callable.

## Tests

Test modules are exempt from the checker. Test docstrings state the behavior
under test in one sentence: `"""A draft order cannot be allocated."""`. The test
name and the docstring together form the specification.

## Anti-patterns

| Anti-pattern | Fix |
| --- | --- |
| `"""Get order."""` on `get_order` | Say what is notable or remove the noise. |
| `Args:` missing a meaning, or a repeated type that differs from the annotation | Write `name: meaning`; if a type adds value, write the matching annotation as `name (type): meaning`. |
| `Args:`/`Returns:` that only repeat a self-evident signature | Prefer concise prose when complete; preserve actual meanings, constraints, units and failures. |
| `Returns:` that only repeats the type | Describe shape, keys, units, ordering, and empty cases. |
| `Raises: Exception` | Name the specific exceptions the body raises. |
| `Raises:` listing callee failures (`OSError`, `SyntaxError`, a helper's domain error) | Remove the entry; mention an essential propagated failure in prose, or raise it in the public method. |
| Sections on a callable with at most one input | Fold the result and raised errors into the summary; add prose only for genuinely complex behavior. |
| `Args:`/`Raises:` on a class docstring | Use `Attributes:`; move arguments and failures to `__init__`/`__post_init__`. |
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
- [pydoclint violation codes (DOC501-DOC503)](https://jsh9.github.io/pydoclint/violation_codes.html)
- [Ruff DOC502: docstring-extraneous-exception](https://docs.astral.sh/ruff/rules/docstring-extraneous-exception/)
- [numpydoc: Raises section](https://numpydoc.readthedocs.io/en/latest/format.html#raises)
- [Sphinx Napoleon: Google style example](https://www.sphinx-doc.org/en/master/usage/extensions/example_google.html)
- [Sphinx reStructuredText Primer: inline markup](https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html#inline-markup)
- [Docutils Quick reStructuredText reference](https://docutils.sourceforge.io/docs/user/rst/quickref.html#inline-markup)
