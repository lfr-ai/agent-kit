# Concrete records and safe narrowing

Reviewed against Python 3.13 and the primary sources below.

## Preserve record shape

Prefer `TypedDict` to `dict[str, str | list[str]]` when each key has a known
type. A `TypedDict` is an ordinary dictionary at runtime, not a parser, validator,
or immutable record. Required keys are required statically; use `NotRequired[T]`
for a possibly missing key, and `T | None` for a present key whose value may be
null. Do not silently fill missing keys while doing a typing-only cleanup.

```python
from typing import TypedDict


class ResourceRecord(TypedDict):
    """Paths for one resource group."""

    name: str
    paths: list[str]
```

Document what the keys mean, whether paths are relative, ordering, empty lists,
and any overlap between lists. An annotation cannot express all these contracts.

## Choose the predicate from its truth table

```python
from typing import TypeGuard, TypeIs


def is_text(value: object) -> TypeIs[str]:
    """Return whether the value is a string, including an empty string."""
    return isinstance(value, str)


def is_nonempty_text(value: object) -> TypeGuard[str]:
    """Accept only strings containing non-whitespace text."""
    return isinstance(value, str) and bool(value.strip())
```

`is_text` accepts every string. In a false branch, a checker can exclude
strings. `is_nonempty_text` rejects some strings, so a false result must **not**
exclude `str`. Its `TypeGuard` promises only that a true result is a string.
The same distinction applies to length limits, legal names, schema subsets,
hash formats, and range checks.

`TypeIs[T]` requires `T` to be compatible with the input type and narrows by
intersection on success. `TypeGuard[T]` can narrow incompatible invariant types,
such as `list[object]` to `list[str]`, but only in the true branch. Checking
mutable contents can become invalid after mutation or an `await`; keep the
validated scope small or copy to an immutable record at the boundary.

Do not mechanically replace `TypeGuard`. Check all values of the target type,
including empty strings/containers, subclasses, and allowed extra record keys.
Neither annotation checks that the implementation is correct.

## Callable forwarding

For a transparent wrapper, `Callable[P, R]` with `ParamSpec` preserves parameter
kinds and the result type. `Callable[..., object]` discards argument information.
Use overloads only for actual distinct call contracts; metadata copied by
`functools.wraps` does not prove forwarding or async behavior is correct.

## Primary sources

- [Python 3.13: TypedDict](https://docs.python.org/3.13/library/typing.html#typing.TypedDict)
- [Python 3.13: TypeIs](https://docs.python.org/3.13/library/typing.html#typing.TypeIs)
- [Python 3.13: TypeGuard](https://docs.python.org/3.13/library/typing.html#typing.TypeGuard)
- [Canonical typing guide: narrowing and soundness](https://typing.python.org/en/latest/guides/type_narrowing.html)
- [PEP 742: narrowing types with TypeIs](https://peps.python.org/pep-0742/)
- [Python 3.13: ParamSpec](https://docs.python.org/3.13/library/typing.html#typing.ParamSpec)
