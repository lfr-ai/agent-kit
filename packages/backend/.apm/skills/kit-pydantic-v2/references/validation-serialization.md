# Pydantic v2 validation and serialization

## Validators

- Prefer `Annotated` constraints, `Field` constraints, and built-in types before custom Python validators.
- Prefer `field_validator(mode='after')` when validated typed input is sufficient. An after validator returns the validated value.
- A before validator receives arbitrary raw input; accept `object`, avoid mutating inputs that may be reused, and return a value the field can validate.
- Use `model_validator(mode='after')` for invariants involving multiple fields; return `self`. Use before/wrap model validators only when the raw-input or handler semantics are required.
- Field validation order follows declaration order. `ValidationInfo.data` contains only fields already validated; avoid hidden ordering dependencies or express the invariant at model level.
- Raise `ValueError` or `PydanticCustomError` for invalid input. `TypeError` is no longer wrapped into `ValidationError` in v2.
- Validators must not perform I/O, mutate external state, or log raw sensitive input.

## Validation entry points

- Use `Model.model_validate(mapping)` for Python data and `Model.model_validate_json(payload)` for JSON.
- Use `TypeAdapter[T]` for arbitrary types without inventing a wrapper model.
- Treat validated output types as the guarantee. Input may be copied, coerced, or normalized depending on configuration.
- Never use `model_construct()` on untrusted input; it bypasses validation.

## Serialization and schema

- `model_dump()` produces Python-mode values; `model_dump(mode='json')` produces JSON-compatible Python values; `model_dump_json()` produces JSON text.
- Select `by_alias`, `exclude_unset`, `exclude_defaults`, and `exclude_none` based on the published wire contract, not convenience. Test each behavior a client relies on.
- Use field/model serializers for intentional representation changes. Avoid serializing internal-only state or secrets.
- `model_json_schema()` describes accepted/produced structure; it is distinct from serializing an instance. Snapshot or assert the contract where it is externally consumed.
- Prefer named `TypeAdapter` instances reused across hot paths rather than rebuilding validators repeatedly. Benchmark before optimizing.
