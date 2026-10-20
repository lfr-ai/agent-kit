# Strict mode and coercion

## Lax by default

Pydantic's default ("lax") mode coerces compatible input: `"42"` becomes `42`
for an `int` field, `1` becomes `True` for `bool`, and an ISO string becomes a
`datetime`. This is convenient for query strings and environment variables but
can hide client bugs at JSON API boundaries.

Strict mode rejects input whose type does not already match. In strict mode:

- `int` rejects `"42"` and `42.0`; `float` still accepts `int`.
- `bool` rejects `1` and `"true"`.
- For Python input, `date`, `datetime`, and `UUID` fields reject strings. If the
  data came from JSON, validate the raw text with `model_validate_json` rather
  than calling `json.loads` first.
- For JSON input, types without a JSON representation (`datetime`, `date`,
  `UUID`, `Decimal`, `bytes`) are still parsed from strings, because JSON has no
  native form for them.

Always confirm specific behavior against the conversion table for the pinned
version.

## Where to apply it

| Scope | How | Use when |
| --- | --- | --- |
| One call | `Model.model_validate(data, strict=True)` | A single entry point needs strict checking |
| One model | `model_config = ConfigDict(strict=True)` | The whole wire contract is typed JSON from trusted clients |
| One field | `Field(strict=True)` or `Annotated[int, Strict()]` | A single field must not be coerced (identifiers, flags) |
| Type aliases | `StrictInt`, `StrictStr`, `StrictBool`, `StrictFloat`, `StrictBytes` | Reusable strict scalars |
| Opt out per field | `Field(strict=False)` inside a strict model | One field legitimately arrives as text |

Strict settings on a model do not automatically apply to nested models that
declare their own config; set them where needed.

## Choosing per boundary

- **JSON APIs between services**: strict for identifiers, amounts, and flags
  catches producer bugs early. Keep lax parsing for timestamps (strings in JSON
  anyway).
- **Query strings, form data, environment variables**: lax mode is appropriate;
  everything arrives as text.
- **Configuration files**: lax for numbers and booleans is usually expected by
  operators.
- **Internal re-validation of trusted objects**: consider `model_construct` only
  for already-validated data from your own code, never for external input.

## Strictness is not validation

Strict mode controls types, not values. A strict `int` still accepts `-1`; add
`Field(ge=0)`. A strict `str` still accepts an empty string; add `min_length`.
Combine strictness with constraints, `Literal`/`Enum` choices, and
`extra="forbid"`.

## Migration risk

Turning on strict mode for an existing public endpoint is a breaking change for
clients that sent numbers as strings. Roll it out with metrics on validation
failures, or apply it to new fields and versions first.

## Testing

- Parametrize over coercible inputs (`"1"`, `1.0`, `True`) and assert rejection
  for strict fields and acceptance for lax ones.
- Test both `model_validate` and `model_validate_json`; the JSON path has
  different rules for string-encoded types. The
  [payment contract tests](../assets/patterns/test_payments.py.template)
  show both paths.

## Sources

- <https://pydantic.dev/docs/validation/latest/concepts/strict_mode/>
- <https://pydantic.dev/docs/validation/latest/concepts/conversion_table/>
- <https://pydantic.dev/docs/validation/latest/api/pydantic/types/#pydantic.types.Strict>
- <https://pydantic.dev/docs/validation/latest/concepts/config/>
