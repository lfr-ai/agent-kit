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
class OrderStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
```

Guidelines:

- Write explicit values; do not use `auto()` for values that are persisted or
  sent over the wire, because renaming a member would then change stored data.
- Decorate with `@enum.unique` to reject accidental aliases.
- Parse untrusted input with `OrderStatus(value)` and translate the resulting
  `ValueError` into the boundary's error format.
- Put behavior that depends on the member on the enum (`def is_terminal(self)`)
  or in an exhaustive `match`; avoid scattered `if status == ...` chains.
- Treat adding a member as a contract change for consumers that switch over it.
- Use `IntEnum` only for interoperability with numeric protocols, and `Flag` for
  combinable bit sets.

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
