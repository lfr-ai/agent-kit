# Polymorphism versus conditionals

Replace a conditional with polymorphism when the same type switch appears in
more than one place, or when new variants are expected. Keep the conditional
when there is one decision, the variants are closed, and the branches are short.

## Decision table

| Situation | Prefer |
| --- | --- |
| One `if`/`match` on a value, closed set, short branches | `match` statement |
| Same switch on a kind repeated in several functions | Polymorphic method per variant |
| Behavior chosen by input type, open for extension by other modules | `functools.singledispatch` |
| Strategy chosen at wiring time | Inject a `Protocol` implementation |
| Data lookup with no behavior | `Mapping[Kind, Value]` constant |
| Variant data with exhaustive handling | `StrEnum` or union of frozen records plus `match` and `assert_never` |

## Pattern: strategy behind a port

```python
class PriceRule(Protocol):
    def apply(self, *, subtotal: Decimal) -> Decimal: ...


@dataclass(frozen=True, kw_only=True, slots=True)
class PercentageDiscount:
    percent: Decimal

    def apply(self, *, subtotal: Decimal) -> Decimal:
        return subtotal * (Decimal(100) - self.percent) / Decimal(100)


@dataclass(frozen=True, kw_only=True, slots=True)
class NoDiscount:
    def apply(self, *, subtotal: Decimal) -> Decimal:
        return subtotal
```

The composition root chooses the rule; the service calls `rule.apply(...)` and
never inspects which rule it holds.

## Pattern: exhaustive match over a closed union

```python
from typing import assert_never

type Payment = CardPayment | BankTransfer


def fee(payment: Payment) -> Decimal:
    match payment:
        case CardPayment(amount=amount):
            return amount * CARD_RATE
        case BankTransfer():
            return Decimal(0)
        case _:
            assert_never(payment)
```

A type checker reports the `assert_never` call as reachable when a new member is
added to the union and not handled, which turns a forgotten branch into a
static error.

## Pattern: singledispatch for open extension

```python
from functools import singledispatch


@singledispatch
def render(item: object) -> str:
    raise TypeError(f"no renderer for {type(item).__name__}")


@render.register
def _(item: Invoice) -> str:
    return f"Invoice {item.number}"
```

Use this when callers in other modules must add variants without editing the
dispatcher. Registration happens at import time, so the module that registers
must be imported by the composition root.

## Pattern: lookup table instead of if-chains

```python
_STATUS_LABELS: Mapping[OrderStatus, str] = MappingProxyType(
    {
        OrderStatus.DRAFT: "Draft",
        OrderStatus.CONFIRMED: "Confirmed",
        OrderStatus.SHIPPED: "Shipped",
    }
)
```

Add a test asserting that every enum member has an entry so the table cannot
fall behind the enum.

## Warning signs

- `isinstance` checks against sibling classes inside business logic.
- A `kind` or `type` string field compared in many places.
- A function with a boolean flag that switches between two algorithms.
- A base class whose methods raise `NotImplementedError` for most subclasses
  (the hierarchy is wrong; split the interface).

## When not to introduce polymorphism

- Only one implementation exists and no second one is planned: keep a function.
- The "strategy" would hold no state and one line of logic: a plain callable
  (`Callable[[Decimal], Decimal]`) is enough.
- Inheritance used only to share helper code: prefer composition or a function.

## Sources

- [PEP 634 - Structural pattern matching](https://peps.python.org/pep-0634/)
- [PEP 544 - Protocols: structural subtyping](https://peps.python.org/pep-0544/)
- [functools.singledispatch](https://docs.python.org/3/library/functools.html#functools.singledispatch)
- [typing.assert_never](https://docs.python.org/3/library/typing.html#typing.assert_never)
- [PEP 695 - Type parameter syntax and type statements](https://peps.python.org/pep-0695/)
