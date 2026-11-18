# Dataclasses and enums

## Records

Default record shape:

```python
@dataclass(frozen=True, kw_only=True, slots=True)
class LineItem:
    sku: str
    quantity: int
    unit_price: Money
```

Why each option:

- `frozen=True`: instances cannot be mutated after validation, so invariants
  checked in `__post_init__` stay true; instances are hashable.
- `kw_only=True`: construction sites name every field; reordering or inserting
  fields is not a silent breaking change.
- `slots=True`: no per-instance `__dict__`, lower memory, and typos in attribute
  assignment fail loudly.

### Validation

Validate in `__post_init__` and raise `ValueError` with a message that names the
field. Keep validation to the record's own invariants; cross-aggregate rules
belong in the domain service or aggregate.

```python
def __post_init__(self) -> None:
    if self.quantity <= 0:
        raise ValueError(f"quantity must be positive, got {self.quantity}")
```

To normalize a field in a frozen dataclass, use
`object.__setattr__(self, "name", normalized)` inside `__post_init__` only, or
prefer a named constructor that normalizes before calling the constructor.

### Derived values and updates

- Derived values: `@property` or `functools.cached_property` (not available with
  `slots=True` unless a `__dict__` slot is declared, so prefer `@property`).
- Updates: `dataclasses.replace(record, quantity=2)`, which runs `__post_init__`
  again, so the new instance is validated too.

### Collections inside frozen records

Frozen means the attribute cannot be rebound, not that its value is immutable.
Use `tuple[...]` and `frozenset[...]` for collection fields, and
`types.MappingProxyType` for read-only mappings.

### Defaults

- Immutable defaults are fine: `currency: str = "EUR"`.
- Collections use `field(default_factory=tuple)`.
- Fields holding secrets use `field(repr=False)`.

### When not to use a dataclass

- Objects with identity and lifecycle (entities, aggregates): use a regular class
  with explicit methods, or a non-frozen dataclass with `eq=False` and an
  identity-based `__eq__`.
- Boundary schemas that need parsing and coercion: use the project's validation
  library (for example Pydantic) at the boundary and convert to domain records.

## Enums

Use `enum.StrEnum` (Python 3.11+) for closed sets of string values that cross a
boundary (JSON, database, CLI):

```python
from enum import StrEnum, auto, unique


@unique
class OrderStatus(StrEnum):
    DRAFT = auto()
    CONFIRMED = auto()
    SHIPPED = auto()
```

Guidelines:

- Use `auto()` when a `StrEnum` member's required value is its lowercase name.
  Keep nonmatching values such as `"in-progress"` or `"stepList"` explicit.
  Preserve numeric protocol values too; ordinary `Enum` auto values can shift
  when members are inserted or reordered.
- Assert serialized values in tests. Renaming a `StrEnum` member using `auto()`
  changes its wire value and needs the same review as any other contract change.
- Ordinary closed enums declare `@enum.unique` or the equivalent
  `@enum.verify(enum.UNIQUE)` to reject accidental aliases. Imported and qualified
  spellings are valid. This is not a blanket ban on intentional aliases, flags
  or small `Literal` contracts; choose those when their semantics fit rather
  than treating them as ordinary unique closed sets.
- Parse untrusted input with `OrderStatus(value)` and translate the resulting
  `ValueError` into the boundary's error format.
- Put behavior that depends on the member on the enum (`def is_terminal(self)`)
  or in an exhaustive `match`; avoid scattered `if status == ...` chains.
- Treat adding a member as a contract change for consumers that switch over it.
- Use `IntEnum` only for interoperability with numeric protocols, and `Flag` for
  combinable bit sets.
- Do not add `@typing.final` to every leaf class; it is unrelated to enum
  uniqueness or module-level `Final` and needs an actual extension contract.

Standard class syntax still requires `= auto()` for each generated member.
There is no standard decorator that removes these assignments. The functional
API can construct an enum from member names, but explicit classes are preferable
for static contracts, member documentation and editor navigation. Do not add a
custom metaclass or dependency just to omit `auto()`.

The bundled `enum-auto` check covers direct `StrEnum` declarations with default
generation. It does not infer custom or mixed-base generation behavior.

## Templates

- [Frozen slotted dataclass](../assets/dataclass.py.template) with
  [tests](../assets/test_dataclass.py.template).
- [StrEnum](../assets/enum.py.template) with
  [tests](../assets/test_enum.py.template).

## Sources

- [dataclasses](https://docs.python.org/3/library/dataclasses.html)
- [enum](https://docs.python.org/3/library/enum.html)
- [Enum HOWTO](https://docs.python.org/3/howto/enum.html)
- [PEP 557 - Data classes](https://peps.python.org/pep-0557/)
- [What's new in Python 3.11: enum](https://docs.python.org/3/whatsnew/3.11.html#enum)
