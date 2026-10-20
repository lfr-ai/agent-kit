# Review a Pydantic v1-to-v2 migration

Use the official migration guide for the installed v2 minor. Check behavior, not only renamed symbols.

Group the renames by what they change, and review each group with its own tests:

| Concern | Before (v1) | After (v2) | What still needs review |
| --- | --- | --- | --- |
| Configuration | inner `class Config` | `model_config = ConfigDict(...)` | Renamed keys such as `orm_mode` and `allow_population_by_field_name` |
| Field checks | `@validator` | `@field_validator` | `pre=True` becomes `mode="before"`; `each_item` has no direct flag |
| Whole-model checks | `@root_validator` | `@model_validator` | Choose `mode="before"` or `"after"` explicitly |
| Reading input | `parse_obj`, `parse_raw` | `model_validate`, `model_validate_json` | Strictness and coercion of each accepted input |
| ORM objects | `from_orm` | `model_validate(obj, from_attributes=True)` | Enable attribute reading only where intended |
| Writing output | `dict`, `json` | `model_dump`, `model_dump_json` | Aliases, `mode="json"`, excluded and default fields |
| Schemas | `schema`, `schema_json` | `model_json_schema` | Generated schema diffs for published contracts |
| Custom root types | `__root__` field | `RootModel[T]` | Serialization shape at the wire boundary |
| Unvalidated copies | `construct`, `copy` | `model_construct`, `model_copy` | Both still bypass validation; `update=` is not checked |

Also review:

- `T | None` is nullable but required unless it has a default.
- Validator ordering, input types, return values, and `TypeError` behavior changed.
- Coercion and conversion behavior may differ; write tests for representative accepted and rejected inputs.
- Equality is between model instances, not model-to-dict comparisons.
- `model_dump` aliases and JSON-compatible mode must match the existing wire contract.
- Remove `pydantic.v1` compatibility imports after all consumers have migrated. Do not add a mixed-version fallback for a v2-only project.

Run [check_pydantic_v2.py](../assets/check_pydantic_v2.py) over the source tree to
list remaining v1 decorators, config keys, `Field` keywords, helpers, and methods
with their v2 replacements before and after each migration step.

Source: [official migration guide](https://pydantic.dev/docs/validation/latest/get-started/migration/).
