# Dunder methods

Special ("dunder") methods integrate a type with Python's protocols. Implement
them only when the protocol has an obvious, unsurprising meaning for the type.

## Prefer generated dunders

`@dataclass(frozen=True, kw_only=True, slots=True)` generates `__init__`,
`__repr__`, `__eq__`, and (because the instance is frozen and `eq=True`)
`__hash__`. Hand-writing these for a record is usually a mistake.

## Equality and hashing

- Value objects: equality by all fields. Let the dataclass generate it.
- Entities and aggregates: equality by identity only. Implement `__eq__` to
  compare the identifier and type, and `__hash__` to hash the identifier.
- If you define `__eq__` on a mutable class, set `__hash__ = None` or make sure
  the hashed fields never change; a hash that changes while the object sits in a
  set corrupts the set.
- Return `NotImplemented` (not `False`) from `__eq__` for unrelated types so
  Python can try the reflected operation.

```python
def __eq__(self, other: object) -> bool:
    if not isinstance(other, Order):
        return NotImplemented
    return self.id == other.id


def __hash__(self) -> int:
    return hash(self.id)
```

## Representation

- `__repr__` is for developers: unambiguous, and ideally valid constructor
  syntax. Exclude secrets and personal data (`field(repr=False)`).
- `__str__` is for end users. Define it only when a natural display form exists,
  for example `Money` rendering as `"12.50 EUR"`.

## Ordering

Implement ordering only for types with one natural total order (dates, versions,
money in one currency). Use `@dataclass(order=True)` or
`functools.total_ordering`. Do not make entities orderable by an arbitrary field.

## Truthiness and size

- Define `__bool__` only when "empty" is meaningful. A value object whose
  truthiness depends on an amount invites `if price:` bugs where zero is valid.
- `__len__` belongs to collections. Implementing it also makes empty instances
  falsy.

## Containers and iteration

- Prefer subclassing `collections.abc` bases (`Sequence`, `Mapping`) so mixin
  methods are correct and consistent.
- `__iter__` should return a fresh iterator each call; an object that is its own
  iterator can only be iterated once.
- `__contains__` must agree with iteration.

## Context managers

Implement `__enter__`/`__exit__` (or `__aenter__`/`__aexit__`) for resources that
must be released. `__exit__` returns `False` (or `None`) unless it deliberately
suppresses the exception. Prefer `contextlib.contextmanager` for simple cases.

## Arithmetic

Implement operators only when semantics are mathematical: `Money + Money` in the
same currency. Raise `ValueError` for mixed currencies rather than converting
silently. Return `NotImplemented` for unsupported operand types.

## Avoid

- `__getattr__` magic that hides missing attributes from type checkers.
- `__del__` for cleanup; use context managers or `weakref.finalize`.
- `__call__` on service classes to save a method name; name the operation.
- Overloading operators for non-mathematical meaning (`order << line`).

## Sources

- [Python data model](https://docs.python.org/3/reference/datamodel.html)
- [dataclasses](https://docs.python.org/3/library/dataclasses.html)
- [functools.total_ordering](https://docs.python.org/3/library/functools.html#functools.total_ordering)
- [collections.abc](https://docs.python.org/3/library/collections.abc.html)
- [contextlib](https://docs.python.org/3/library/contextlib.html)
