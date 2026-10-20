# Custom serialization

## Choose the narrowest tool

| Need | Tool |
| --- | --- |
| Change one field's output everywhere | `Annotated[T, PlainSerializer(func, return_type=...)]` |
| Adjust one field's default output | `Annotated[T, WrapSerializer(func)]` or `@field_serializer(..., mode="wrap")` |
| Change output only for JSON | `when_used="json"` (or `"json-unless-none"`) on the serializer |
| Add a derived output field | `@computed_field` on a property |
| Reshape the whole model | `@model_serializer` (plain or `mode="wrap"`) |
| Different wire names | `serialization_alias` and `model_dump(by_alias=True)` |
| Hide internal state | `Field(exclude=True)` or private attributes (`_name`) |

Prefer annotated serializers on reusable types (`Money`, `UtcDatetime`) over
per-model decorators; the behavior then travels with the type.

## Examples

```python
Money = Annotated[
    Decimal,
    PlainSerializer(lambda value: f"{value:.2f}", return_type=str, when_used="json"),
]


class Invoice(BaseModel):
    number: str
    total: Money
    issued_at: datetime

    @field_serializer("issued_at", when_used="json")
    def _utc_iso(self, value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @computed_field
    @property
    def is_paid(self) -> bool:
        return self.total == 0
```

- `model_dump()` (Python mode) keeps `Decimal`; `model_dump(mode="json")` and
  `model_dump_json()` produce the string.
- Computed fields appear in output and in the serialization JSON Schema, not in
  validation input. Keep them cheap and side-effect free.

## Subclasses and `SerializeAsAny`

A field annotated with a parent model type serializes only the parent's fields,
even when the value is a subclass instance. This prevents accidental data
leakage from subclasses. When polymorphic output is intended, annotate the field
with `SerializeAsAny[Parent]`, pass `serialize_as_any=True` to the dump call, or
use a discriminated union, which is usually the clearer contract.

## Round trips

- `model_dump(round_trip=True)` produces output suitable for validating back
  into an equal model (for example JSON-in-string fields stay encoded).
- If a serializer changes representation (a `Decimal` to a string), make sure
  the field also validates from that representation; lax mode does this for
  most standard types.
- Test `Model.model_validate_json(model.model_dump_json()) == model` for every
  externally stored model.

## Performance notes

- Serializers written in Python run for every value; annotated
  `PlainSerializer` functions on hot paths should be trivial.
- `model_dump_json()` is faster than `json.dumps(model.model_dump(mode="json"))`
  because serialization stays in the core.
- `exclude_unset`, `exclude_defaults`, and `exclude_none` change the wire
  contract; choose them per endpoint, not per convenience.

The [payment contract pattern](../assets/patterns/payments.py.template) shows an
annotated `Money` serializer, a JSON-only datetime serializer, and a computed
field.

## Sources

- <https://pydantic.dev/docs/validation/latest/concepts/serialization/>
- <https://pydantic.dev/docs/validation/latest/api/pydantic/functional_serializers/>
- <https://pydantic.dev/docs/validation/latest/concepts/fields/#the-computed_field-decorator>
- <https://pydantic.dev/docs/validation/latest/concepts/alias/>
