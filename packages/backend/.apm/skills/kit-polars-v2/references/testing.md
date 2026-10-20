# Testing Polars pipelines

## Structure code for testing

- Write transformations as functions `LazyFrame -> LazyFrame` with no I/O. The
  scan and sink live in a thin adapter. Tests pass `pl.LazyFrame({...})` built
  from literals.
- Keep schema contracts as constants so tests and production share them.
- Keep sorting at the output boundary so tests can rely on order.

## Assertions

- `polars.testing.assert_frame_equal(actual, expected)` compares values,
  dtypes, column order, and row order. Relax only what the contract allows:
  `check_row_order=False` when order is unspecified, `check_column_order=False`
  when consumers select by name, and float tolerances for computed decimals.
- Build `expected` with explicit dtypes (`schema=` argument) so a silent dtype
  change fails the test.
- `assert_series_equal` for single-column checks.
- Assert the schema separately with `lf.collect_schema() == CONTRACT` to catch
  dtype drift without running the full pipeline.

## Cases worth writing

| Case | Why |
| --- | --- |
| Empty input | Aggregations and joins on zero rows keep the schema |
| All-null column | Null semantics of sums, means, and comparisons |
| Duplicate keys | Joins multiply rows; group-bys merge them |
| Mixed generations of source files | Casts and missing columns |
| Boundary values | Decimal precision, integer overflow, timezone edges |
| Non-ASCII strings | String length, slicing, case mapping |
| Unknown categories | `Enum` casts fail on values outside the list |

## Property-based tests

`polars.testing.parametric` provides Hypothesis strategies such as
`dataframes()` and `column()` that generate frames with chosen dtypes and null
probabilities. Use them for invariants rather than exact outputs:

- the number of groups never exceeds the number of input rows,
- filtering then aggregating equals aggregating a pre-filtered frame,
- a round trip through `write_parquet`/`read_parquet` preserves the frame.

Keep example counts modest in CI and fix a seed profile for reproducibility.

## Testing the real scan path

A `LazyFrame` built from literals does not exercise file scanning, predicate
pushdown, or schema inference. Add one integration test per adapter that writes
a small Parquet or CSV file to `tmp_path`, runs the production scan function,
and compares the result. Use `lf.explain()` text only for coarse checks (for
example that a filter appears in the scan node), since plan formatting changes
between releases.

## Performance tests

Do not put wall-clock thresholds in unit tests. Benchmark separately on
representative data, record results with the Polars version, and compare runs
on the same hardware.

The [schema contract tests](../assets/patterns/test_schema_contract.py.template)
and the existing [pipeline test](../assets/test_lazy_pipeline.py.template) show
these patterns.

## Sources

- <https://docs.pola.rs/api/python/stable/reference/testing.html>
- <https://docs.pola.rs/api/python/stable/reference/api/polars.testing.assert_frame_equal.html>
- <https://docs.pola.rs/api/python/stable/reference/api/polars.testing.parametric.dataframes.html>
- <https://hypothesis.readthedocs.io/en/latest/>
- <https://docs.pytest.org/en/stable/how-to/tmp_path.html>
