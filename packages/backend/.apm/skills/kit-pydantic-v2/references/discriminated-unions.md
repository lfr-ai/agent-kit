# Discriminated (tagged) unions

## Why tag unions

A plain `A | B | C` union makes Pydantic try members until one validates (in
"smart" mode it scores candidates). That is slower, can pick an unintended
member when shapes overlap, and produces one error per member when nothing
matches. A discriminated union reads one field, selects exactly one member, and
reports errors for that member only.

## Literal discriminator

```python
class CardPayment(BaseModel):
    kind: Literal["card"]
    last4: Annotated[str, StringConstraints(pattern=r"^\d{4}$")]


class BankPayment(BaseModel):
    kind: Literal["bank"]
    iban: str


Payment = Annotated[CardPayment | BankPayment, Field(discriminator="kind")]
```

- Every member declares the discriminator as a `Literal` (or several literals for
  aliases of one member). Values must be unique across members.
- Validation errors name the problem precisely: a missing tag (`union_tag_not_found`)
  or an unknown tag (`union_tag_invalid`, listing the expected tags).
- The discriminator can be an alias when the wire name differs; set the alias on
  each member's field.
- Generated JSON Schema includes `oneOf` with a `discriminator` mapping, which
  OpenAPI clients use to generate tagged types.

## Callable discriminator

When the tag is not a single field (legacy payloads, a type inferred from
structure), use `Discriminator` with a function and `Tag` annotations:

```python
def payment_tag(value: object) -> str | None:
    if isinstance(value, dict):
        return "card" if "last4" in value else "bank" if "iban" in value else None
    return getattr(value, "kind", None)


Payment = Annotated[
    Annotated[CardPayment, Tag("card")] | Annotated[BankPayment, Tag("bank")],
    Discriminator(payment_tag),
]
```

The function receives raw input (dicts for Python/JSON input, instances when
re-validating models) and must handle both. Return `None` to produce a clear
"unable to extract tag" error.

## Nesting and lists

- Discriminated unions can nest: an outer union by `category`, an inner union by
  `kind`.
- For a list of events, annotate the item type: `list[Payment]`. Use a
  `TypeAdapter(list[Payment])` built once when validating outside a model.

## Evolving a union

- Adding a member is backward compatible for readers that ignore unknown tags
  only if they actually do. Pydantic rejects unknown tags by default; decide
  whether consumers should fail or route unknown events to a fallback member
  (for example a `kind: str` catch-all validated with a callable discriminator).
- Removing a member is breaking for any stored or in-flight payloads.
- Renaming a tag requires accepting both values for a migration window
  (`Literal["card", "credit_card"]`) and writing the new value.

## Smart and left-to-right modes

For unions that cannot be tagged (for example `int | str`), the default smart
mode prefers exact type matches and then the member with the most valid fields.
`Field(union_mode="left_to_right")` tries members in declaration order and
returns the first success; use it only when declaration order is the intended
priority.

## Testing

- One valid payload per member, asserting the selected class.
- Missing tag and unknown tag, asserting the error type.
- Round trip: `model_dump(mode="json")` then validate again produces an equal
  value.
- JSON Schema snapshot when clients generate code from it.

The [payment contract pattern](../assets/patterns/payments.py.template) and its
[tests](../assets/patterns/test_payments.py.template) implement these checks.

## Sources

- <https://pydantic.dev/docs/validation/latest/concepts/unions/>
- <https://pydantic.dev/docs/validation/latest/api/pydantic/types/#pydantic.types.Discriminator>
- <https://pydantic.dev/docs/validation/latest/errors/validation_errors/>
- <https://pydantic.dev/docs/validation/latest/concepts/json_schema/>
