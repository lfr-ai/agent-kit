# Polars schemas, expressions, and tests

## Schema and casts

- Prefer source schema metadata or explicit `schema_overrides` at ingestion when types are part of the contract.
- Use `LazyFrame.collect_schema()` to inspect resolved columns/types before executing an expensive plan.
- Cast explicitly at the boundary. Choose strict/non-strict behavior based on whether invalid data is a failure or a documented null conversion.
- Treat `pl.concat` coercion and `is_in` casts as correctness decisions; v2 is stricter in several paths. Test mismatched dtypes.
- Null and floating-point NaN are different values; select the appropriate null/NaN predicates and fill behavior.

## Expressions

- Express column work with `pl.col` and native expression namespaces (`str`, `list`, `dt`, `struct`, `map`) so Polars can optimize and parallelize.
- Use `with_columns` for independent derived columns and `group_by(...).agg(...)` for grouped computation.
- Python UDFs inhibit optimization and add Python-call overhead. Prefer native expressions or an expression plugin. When unavoidable, choose `map_elements` versus `map_batches` deliberately, provide `return_dtype`, and test null/group behavior.
- Do not assume a selector is interchangeable with a column expression; use selectors for schema-wide selection and `pl.col` for expression operations.

## Contract tests

- Use `polars.testing.assert_frame_equal` and explicit expected dtypes.
- Test empty input, nulls, duplicate keys, non-ASCII/string edge values, and casts where they matter.
- Sort outputs by stable keys before comparison unless preserved row order is a requirement.
- Test lazy semantics through the production scan/query path where practical; a `DataFrame.lazy()` fixture alone does not prove scan pushdown.
- Benchmark on representative data before introducing timing gates; keep correctness tests deterministic.
