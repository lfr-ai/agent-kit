# Validation and serialization performance

Measure before optimizing. Use a representative payload, a warm process, and a
micro-benchmark (`timeit` or `pytest-benchmark`) around the exact call path.
Most of the items below matter only on hot paths (high-volume ingestion,
large lists, per-row validation).

## Build validators once

- Model classes build their core schema at class creation. Do the same for
  non-model types: create `TypeAdapter(list[Order])` at module level or in a
  cached factory, never inside a request handler or loop.
- `defer_build=True` in `ConfigDict` postpones schema building to first use,
  which shortens import time for large model graphs that are not all used.
- Forward references that cannot be resolved at class creation force a rebuild;
  call `Model.model_rebuild()` once at startup instead of paying for it lazily.

## Parse JSON in the core

- `Model.model_validate_json(raw)` and `adapter.validate_json(raw)` parse and
  validate in one pass in Rust. They are faster than `json.loads` followed by
  `model_validate`, and they apply JSON-specific rules (string-encoded dates).
- Likewise `model_dump_json()` beats `json.dumps(model_dump(mode="json"))`.

## Choose cheap types

- Use concrete container types (`list[int]`, `tuple[int, ...]`, `dict[str, int]`)
  rather than abstract ones (`Sequence`, `Mapping`), which need extra checks to
  preserve the input type.
- Tag unions with a discriminator; see
  [discriminated unions](discriminated-unions.md).
- `TypedDict` validates faster than a nested `BaseModel` when you do not need
  model behavior on the nested value.
- `Literal` choices validate faster than wide unions and give clearer errors.
- Avoid `Any` for data you then validate again manually.
- For long lists where the first error is enough, `Annotated[list[int],
  FailFast()]` stops at the first invalid item.

## Keep validators lean

- Built-in constraints (`Field(ge=...)`, `StringConstraints`, `pattern`) run in
  the core. A Python `field_validator` adds a call per value.
- `mode="after"` validators receive already-typed data and are simpler and safer
  than `mode="before"` normalization.
- Avoid `mode="wrap"` validators on hot paths; they are the most expensive form
  because they wrap the inner validation with a Python call and handler.
- Do no I/O, logging, or global lookups inside validators.

## Avoid repeated work

- Do not re-validate the same data at every layer. Validate at the boundary, then
  pass the model or converted domain values inward.
- `revalidate_instances` defaults to `"never"`; keep it unless instances can be
  mutated into invalid states before reuse.
- `model_construct()` skips validation and is appropriate only for data your own
  code already validated (for example rows read back from a typed store).
- `cache_strings` (default enabled) speeds up JSON parsing of repeated keys and
  values; leave it on unless memory is constrained.

## Profiling checklist

1. Confirm the schema is built once (no `TypeAdapter` in loops).
2. Confirm JSON entry points use `*_json` methods.
3. Count Python validators and serializers on the hot model.
4. Check unions for missing discriminators.
5. Re-measure after each change; keep only changes with a measurable gain.

## Sources

- <https://pydantic.dev/docs/validation/latest/concepts/performance/>
- <https://pydantic.dev/docs/validation/latest/concepts/type_adapter/>
- <https://pydantic.dev/docs/validation/latest/concepts/validators/>
- <https://pydantic.dev/docs/validation/latest/api/pydantic/config/>
- <https://docs.python.org/3/library/timeit.html>
