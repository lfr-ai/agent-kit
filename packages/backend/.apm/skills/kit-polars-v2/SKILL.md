---
name: kit-polars-v2
description: Use when building or upgrading Polars 2 DataFrame, LazyFrame, expression, streaming, schema, or Parquet/CSV pipelines.
license: MIT
---

# Build predictable Polars 2 pipelines

1. Read the consumer lockfile and confirm Polars major/minor. Consult the official v2 upgrade guide when migrating; do not infer APIs from older examples.
2. Keep Polars frames at the data-processing adapter/service boundary. Convert to domain values before entering framework-independent Core.
3. Prefer `scan_*` plus `LazyFrame` for file-backed, multi-step, or larger-than-memory work so projection/predicate pushdown and the optimizer can act. Use eager `DataFrame` for small in-memory work or eager-only operations.
4. Express transformations with `pl.col`, `select`, `with_columns`, `filter`, `group_by`, and `agg`. Avoid Python row loops and eager materialization between compatible lazy steps.
5. In Polars 2, lazy `collect(engine='auto')` uses streaming by default. Do not assume row order from joins, grouping, or reshape operations; sort explicitly for deterministic output or request `maintain_order=True` when preserving input order is a real contract.
6. Inspect lazy schemas with `collect_schema()` and validate required names/types before expensive execution. Make casts, null behavior, and incompatible concatenation policy explicit.
7. Keep null and NaN semantics distinct. Test empty, null, mixed-type, and ordering cases that affect the business result.
8. Avoid `map_elements` and Python UDFs when expressions, built-ins, or plugins can express the operation. If a UDF is necessary, define `return_dtype`, document the boundary, and benchmark realistic data.
9. Prefer streaming sinks for large results where supported rather than collecting a full frame only to write it. Verify sink semantics and ordering in the pinned version.
10. Test results with `polars.testing.assert_frame_equal`; sort both sides if ordering is not a contract. Do not use flaky runtime-only speed thresholds.
11. For migration, inspect removed APIs and semantic default changes in the [v2 upgrade guide](references/upgrade-to-v2.md); migrate one behavior at a time with regression coverage.
12. Use the [lazy pipeline](assets/lazy_pipeline.py.template) and [contract test](assets/test_lazy_pipeline.py.template) as small starting points.
13. Declare input and output contracts as `pl.Schema` constants, check `collect_schema()` before execution, conform with strict casts, and assert null and duplicate keys; see [schema contracts](references/schema-contracts.md) and the [contract pattern](assets/patterns/schema_contract.py.template) with its [tests](assets/patterns/test_schema_contract.py.template).
14. Scan, transform lazily, and materialize once; inspect `explain()` for pushdown and sink large outputs; see [lazy execution and streaming](references/lazy-streaming.md) and the [streaming export](assets/patterns/streaming_export.py.template).
15. Test empty, null, duplicate-key, boundary, and real-scan cases, and use property-based strategies for invariants; see [testing pipelines](references/testing.md).
16. Run [check_polars_usage.py](assets/check_polars_usage.py) on source directories to find Python UDFs without `return_dtype`, row loops, eager-then-lazy reads, mid-pipeline collects, and renamed APIs; mark a reviewed exception with `# polars: reviewed`.

## Acceptance gates

- Pipeline inputs and outputs have declared schemas that are checked before expensive execution.
- Observable row order is set by an explicit sort at the output boundary or documented as unspecified and tested accordingly.
- No unreviewed Python UDFs, row loops, or mid-pipeline `collect()` calls remain in hot paths.
- Tests cover empty, null, duplicate-key, and dtype-drift cases plus one real scan per adapter.
- Performance claims are backed by a benchmark on representative data with the pinned Polars version.

## Commands

```text
python assets/check_polars_usage.py src
python assets/check_polars_usage.py --self-test
pytest tests/unit/analytics -q
```

## Focused references

- [Polars 2 execution and order semantics](references/v2-execution.md)
- [Schemas, expressions, UDFs, and testing](references/schema-expressions-testing.md)
- [Polars 2 upgrade checklist](references/upgrade-to-v2.md)
- [Lazy execution, streaming, and sinks](references/lazy-streaming.md)
- [Schema contracts](references/schema-contracts.md)
- [Testing pipelines](references/testing.md)

Sources: [Polars 2 release](https://pola.rs/posts/release-polars-2),
[v2 upgrade guide](https://docs.pola.rs/releases/upgrade/2/),
[lazy API](https://docs.pola.rs/user-guide/lazy/using/),
[schemas](https://docs.pola.rs/user-guide/lazy/schemas/),
[expressions](https://docs.pola.rs/user-guide/expressions/),
[Python UDFs](https://docs.pola.rs/user-guide/expressions/user-defined-python-functions/),
and [aggregation](https://docs.pola.rs/user-guide/expressions/aggregation/).
