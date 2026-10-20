# Value objects

A value object describes a characteristic of something. It has no identity,
is immutable, and two value objects with the same attributes are equal.

## When to introduce one

Introduce a value object when a primitive carries rules or units:

- Money (amount plus currency, rounding rules).
- Quantities with units, percentages, date ranges, time windows.
- Identifiers with a format (`OrderId`, `Sku`, `EmailAddress`).
- Composite concepts that are always used together (address, coordinates).

Do not wrap a primitive that has no rule, unit, or behavior; a type alias or the
plain type is clearer.

## Python shape

```python
@dataclass(frozen=True, kw_only=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError(
                f"currency must be an ISO 4217 code, got {self.currency!r}"
            )
        if self.amount.as_tuple().exponent < -2:
            raise ValueError("amount supports at most two decimal places")
```

- Frozen: no mutation after validation.
- Keyword-only: call sites name the fields.
- Slotted: compact and protected against attribute typos.
- Validation in `__post_init__`; normalization in a named factory such as
  `Money.parse("12.50 EUR")`.

## Behavior belongs on the value

Operations that combine or transform values return new values:
`Money.add(other)`, `DateRange.overlaps(other)`, `Quantity.split(parts)`.
Operations reject mismatched units (different currencies) instead of converting
silently.

## Precision and units

- Use `decimal.Decimal` or integer minor units for money, never `float`.
- Store time as timezone-aware `datetime` in UTC; convert at the presentation
  boundary.
- Put units in the type (`Duration`, `Weight`) or the field name
  (`timeout_seconds`).

## Single-field wrappers

For identifiers, a single-field frozen dataclass or `typing.NewType` both work.
`NewType` has no runtime cost but no runtime validation; use a dataclass when
the format must be checked.

## Persistence and transport

Value objects are flattened into columns or embedded documents by adapters.
Transport schemas map to and from them at the boundary; the domain never imports
the schema class.

## Testing

- Construction accepts valid values and rejects each invalid case with a clear
  message.
- Equality and hashing follow value semantics.
- Operations preserve invariants. Property-based tests are a good fit: for
  example, adding then subtracting the same amount returns the original, and
  any generated valid input constructs successfully. See
  [test_value_object_properties.py.template](../assets/test_value_object_properties.py.template).

## Templates

[value_object.py.template](../assets/value_object.py.template) and
[test_value_object.py.template](../assets/test_value_object.py.template).

## Sources

- [Martin Fowler: Value Object](https://martinfowler.com/bliki/ValueObject.html)
- [Eric Evans: Domain-Driven Design Reference](https://www.domainlanguage.com/ddd/reference/)
- [dataclasses](https://docs.python.org/3/library/dataclasses.html)
- [decimal](https://docs.python.org/3/library/decimal.html)
- [typing.NewType](https://docs.python.org/3/library/typing.html#newtype)
- [Hypothesis documentation](https://hypothesis.readthedocs.io/en/latest/)
