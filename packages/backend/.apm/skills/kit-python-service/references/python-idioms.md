# Python idioms for typed services

Reviewed 2026-10-23 for Python 3.13 (the toolkit baseline) with notes for 3.14.
Each section gives the rule, a short bad and good example, and the reason.
Topics with a dedicated reference link to it instead of repeating it.

## Parameters

### Positional-only `/` and keyword-only `*`

```python
# Bad: every parameter can be passed either way; renames break callers.
def resize(image, width, height, keep_ratio=True): ...


# Good: the subject is positional-only, options are keyword-only.
def resize(
    image: Image, /, *, width: int, height: int, keep_ratio: bool = True
) -> Image: ...
```

Positional-only (PEP 570) frees you to rename the subject; keyword-only
(PEP 3102) makes call sites self-describing and removes the boolean trap.
Details: [signature design](signature-design.md). Ruff: `FBT001`-`FBT003`.

### Never repeat a default at the call site

```python
def export(
    report: Report, *, limit: int = DEFAULT_LIMIT, strict: bool = False
) -> bytes: ...


export(report, limit=DEFAULT_LIMIT, strict=False)  # Bad: restates the defaults.
export(report)  # Good: the callee owns its defaults.
export(report, strict=True)  # Good: only the deliberate deviation is written.
```

A repeated default silently pins the old value when the callee's default
changes, and hides which arguments the caller actually chose. Ruff has no rule
for this; run `check_python.py --redundant-defaults` (module-level callees only).

### Abstract inputs, concrete outputs

```python
# Bad: forces callers to build a list and hides what the function returns.
def total(lines: list[Line]) -> Iterable[Decimal]: ...


# Good: accept any sequence, return a concrete, documented type.
def total(lines: Sequence[Line]) -> Decimal: ...
def by_sku(lines: Iterable[Line]) -> dict[str, Line]: ...
```

Accept `Iterable`, `Sequence`, `Mapping`, or a `Protocol`; return `list`,
`dict`, a tuple, or a frozen record. `Mapping` also documents that the function
will not mutate the argument.

## Expressions

### Walrus operator `:=` (PEP 572)

```python
# Good: binds a value that the condition and the body both need.
if (match := PATTERN.fullmatch(text)) is None:
    raise ValueError(text)
while chunk := stream.read(CHUNK_SIZE):
    sink.write(chunk)

# Bad: hides an assignment inside a long expression for no reuse.
send(user := load_user(user_id), audit=(count := len(user.roles)) > 0)
```

Use it when it removes a duplicated call or a priming read before a loop. Do not
use it to save one line, in comprehension conditions that become hard to read,
or at statement level where `=` works.

### Named numbers

```python
# Bad
if retries > 3 and elapsed > 30.0:
    ...
# Good
MAX_RETRIES = 3
TIMEOUT_SECONDS = 30.0
if retries > MAX_RETRIES and elapsed > TIMEOUT_SECONDS:
    ...
```

Name every literal other than `0`, `1`, and `-1` with intent and unit. Ruff
`PLR2004` covers comparisons; `check_python.py --magic-numbers` covers all
non-constant positions.

## Closed sets and constants

### Enums instead of string literals

| Need | Use |
| --- | --- |
| Closed set of text values crossing a boundary (status, kind) | `enum.StrEnum` with explicit values and `@enum.unique` |
| Closed set of integers for a numeric protocol | `enum.IntEnum` |
| Combinable options | `enum.Flag` (`Permission.READ \| Permission.WRITE`) |
| Two or three literal values in one signature, no behavior | `typing.Literal["asc", "desc"]` |
| Open set (user-defined tags) | `str` validated at the boundary |

```python
# Bad: typos compile, and every caller re-validates.
def transition(order: Order, status: str) -> None: ...
# Good
def transition(order: Order, status: OrderStatus) -> None: ...
```

Persist and send enum values, never names or ordinals. Details and the enum
template: [dataclasses and enums](dataclasses-enums.md).

### `typing.Final` (PEP 591)

```python
API_VERSION: Final = "2026-10-01"  # public constant: annotated, never rebound
_RETRY_DELAY_SECONDS = 0.5  # private constant: unannotated toolkit convention
```

Annotate public module constants with `Final` so a type checker rejects
rebinding. Toolkit convention leaves private `_UPPER` constants unannotated.
`Final` does not make a mutable value immutable; pair it with a tuple,
`frozenset`, or `types.MappingProxyType`.

### Immutable collections

```python
# Bad: any importer can append to the shared default.
ALLOWED_CURRENCIES = ["EUR", "USD"]
# Good
ALLOWED_CURRENCIES: Final = frozenset({"EUR", "USD"})
SORT_FIELDS: Final = MappingProxyType({"created": "created_at"})
```

Use `tuple` for ordered fixed data and `frozenset` for membership tests; frozen
dataclass fields hold tuples, not lists.

## Types

### What to annotate

| Annotate | Skip |
| --- | --- |
| Every parameter and return of public and private functions and methods (`ANN` rules) | Local variables whose type is obvious from the right-hand side |
| Public module constants (`Final`) and class attributes | `self` and `cls` |
| Empty collections whose element type cannot be inferred (`seen: set[str] = set()`) | Loop variables and comprehension targets |
| `-> None` on initializers and procedures | Lambdas (use a named function when a type matters) |

Use built-in generics (PEP 585: `list[str]`), unions with `|` (PEP 604), and the
type parameter syntax (PEP 695): generic functions declare `[T]` after their
name, and aliases use `type Pair = tuple[int, int]`. Ruff `UP006`, `UP007`,
`UP040`, `UP046`, and `UP047` modernize older spellings. Do not quote
annotations; order definitions so names exist, or rely on Python 3.14 deferred
evaluation (PEP 649 and PEP 749) once the baseline moves.

### `typing.override` (PEP 698)

```python
class JsonExporter(Exporter):
    @override
    def export(self, report: Report) -> bytes: ...
```

The type checker then reports a method that no longer overrides anything after
the base class renames it. Use it on every intentional override, including
`Protocol` implementations that subclass the protocol explicitly.

### `Annotated` (PEP 593)

```python
# Good: the framework reads the metadata.
PositiveInt = Annotated[int, Field(gt=0)]


# Bad: documentation that nothing enforces.
def charge(amount: Annotated[int, "cents"]) -> None: ...
```

Use `Annotated` only when a framework consumes the metadata (validation,
dependency injection, CLI parsing); put units in names or value types instead.

### Record type decision table

| Type | Choose when | Avoid when |
| --- | --- | --- |
| `@dataclass(frozen=True, kw_only=True, slots=True)` | Domain value objects and internal records with validation in `__post_init__` | Untrusted input that needs parsing and coercion |
| `typing.NamedTuple` | Small immutable records that must also unpack or index like tuples | Records that will grow fields; positional construction invites mistakes |
| `typing.TypedDict` (PEP 589, 655 `Required`/`NotRequired`, 692 `**kwargs: Unpack[...]`) | Typing existing dict-shaped data (JSON, driver parameters) without copying it | Values with behavior or invariants: no runtime validation |
| Pydantic `BaseModel` | Boundary schemas: request bodies, settings, external payloads | Domain core; convert to a dataclass at the boundary |
| `typing.Protocol` (PEP 544) | Describing a collaborator's interface for injection | Holding data |

Variadic generics (`TypeVarTuple`, PEP 646) are for array-shape and
callable-forwarding libraries; application code rarely needs them. Libraries
that generate dataclass-like classes mark the decorator with
`typing.dataclass_transform` (PEP 681) so checkers understand the fields.

### `Protocol` versus `ABC`

| Protocol | ABC |
| --- | --- |
| Structural: any class with matching members conforms | Nominal: classes must inherit |
| Ports owned by the core, implemented by adapters and test fakes | Shared base implementation (template method) or registration of virtual subclasses |
| No runtime check unless `@runtime_checkable` (members only, not signatures) | `abstractmethod` prevents instantiating incomplete subclasses |

Default to `Protocol` for injected collaborators; use an ABC only when
subclasses genuinely share code. See [polymorphism](polymorphism.md).

## Classes

### Dunder methods

Let `@dataclass` generate `__init__`, `__repr__`, `__eq__`, and `__hash__`.
When writing them by hand, keep `__eq__` and `__hash__` consistent (equal objects
hash equal; mutable objects with value equality set `__hash__ = None`), return
`NotImplemented` for foreign types, and keep secrets out of `__repr__`. Prefer
`slots=True` (or `__slots__`) for many small instances. Ruff `PLW1641` reports
`__eq__` without `__hash__`. Details: [dunder methods](dunder-methods.md).

### Properties versus methods

```python
@property
def total(self) -> Money:  # Good: cheap, side-effect free, derived state.
    return sum((line.amount for line in self.lines), start=Money.zero(self.currency))


def fetch_rates(self) -> RateTable: ...  # Good: I/O or cost belongs in a method.


@property
def rates(self) -> RateTable:  # Bad: hides a network call behind attribute access.
    return self._client.get_rates()
```

A property must be fast, deterministic, and free of I/O and mutation; anything
that can fail, block, or take arguments is a method named with a verb.

### Underscore conventions

| Spelling | Meaning |
| --- | --- |
| `_name` | Internal to the module or class; not part of the public API |
| `__name` | Name mangling to avoid subclass clashes; rarely needed, avoid by default |
| `name_` | Avoids a keyword or builtin clash (`class_`, `type_`) |
| `_` | Deliberately unused value |
| `__all__` | Explicit public names of a package `__init__` |

Do not reach into another object's `_private` members (Ruff `SLF001`); add a
public method or move the behavior.

### Member and module order

Modules: docstring, imports (stdlib, third party, first party), constants and
type aliases, public types and functions, private helpers below their caller,
`main()` and the entry guard. Classes: docstring and class constants, fields or
`__slots__`, construction, properties, public methods, dunders, private
helpers. Details and the bundled checker: [method ordering](method-ordering.md).

## Functions and decorators

### Decorators with `ParamSpec` (PEP 612)

```python
from collections.abc import Callable
import functools
import logging

logger = logging.getLogger(__name__)


def logged[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    """Return a typed transparent synchronous wrapper."""

    @functools.wraps(function)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        logger.debug("calling wrapped callable")
        return function(*args, **kwargs)

    return wrapper
```

`ParamSpec` preserves the wrapped signature for callers and type checkers;
`Callable[..., Any]` erases it. The example uses Python 3.13-compatible inline
type parameters (PEP 695; Ruff `UP047`). Apply `functools.wraps` to transparent
function wrappers, but do not confuse copied metadata with actual invocation
semantics: this synchronous example does not make an async target's wrapper
an `async def`. Use the [callable decision guide](callables-and-decorators.md)
for partial application, descriptor binding, decorator order and async cases.

## Errors, docstrings, and logging

- Give each package one base exception and specific subclasses ending in
  `Error` (Ruff `N818`); carry structured attributes, chain with `from`. See
  [error handling](error-handling.md).
- Document every exception a function raises directly, or deliberately lets
  propagate as part of its contract, in a `Raises:` section; do not list
  incidental failures of dependencies. Ruff's pydoclint rule `DOC501` (preview
  at review date) reports raised exceptions missing from the section. `DOC502`
  counts only direct `raise` statements, so it flags documented propagated
  exceptions; leave it off rather than suppressing it.
  See [docstrings](docstrings.md) and PEP 257.
- Use a module logger, `logger = logging.getLogger(__name__)`, and lazy `%`
  arguments: `logger.info("order %s confirmed", order_id)`. Never pass
  f-strings, `str.format`, or concatenation to a log call (Ruff `G001`-`G004`)
  or log through the root logger (`LOG015`). See [logging](logging.md).

## Primary sources

- [PEP 8: style guide](https://peps.python.org/pep-0008/)
- [PEP 257: docstring conventions](https://peps.python.org/pep-0257/)
- [PEP 484: type hints](https://peps.python.org/pep-0484/)
- [PEP 544: protocols](https://peps.python.org/pep-0544/)
- [PEP 570: positional-only parameters](https://peps.python.org/pep-0570/)
- [PEP 572: assignment expressions](https://peps.python.org/pep-0572/)
- [PEP 585: generic built-in collections](https://peps.python.org/pep-0585/)
- [PEP 589: TypedDict](https://peps.python.org/pep-0589/)
- [PEP 591: Final](https://peps.python.org/pep-0591/)
- [PEP 593: Annotated](https://peps.python.org/pep-0593/)
- [PEP 604: union operator](https://peps.python.org/pep-0604/)
- [PEP 612: ParamSpec](https://peps.python.org/pep-0612/)
- [PEP 646: variadic generics](https://peps.python.org/pep-0646/)
- [PEP 655: Required and NotRequired](https://peps.python.org/pep-0655/)
- [PEP 681: dataclass_transform](https://peps.python.org/pep-0681/)
- [PEP 692: Unpack for kwargs](https://peps.python.org/pep-0692/)
- [PEP 695: type parameter syntax](https://peps.python.org/pep-0695/)
- [PEP 698: override decorator](https://peps.python.org/pep-0698/)
- [PEP 749: implementing deferred annotations](https://peps.python.org/pep-0749/)
- [typing module documentation](https://docs.python.org/3/library/typing.html)
- [enum module documentation](https://docs.python.org/3/library/enum.html)
- [Ruff rules](https://docs.astral.sh/ruff/rules/)
