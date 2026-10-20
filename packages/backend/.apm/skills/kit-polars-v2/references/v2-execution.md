# Polars 2 execution and ordering

## Lazy by default for pipelines

- `scan_csv`, `scan_parquet`, and other lazy scans allow projection and predicate pushdown before data is read.
- Keep compatible transformations on `LazyFrame`; cross to `DataFrame` only for a documented eager-only operation or a small result that must be materialized.
- `collect_schema()` resolves the lazy schema without collecting the full result. It may still need source metadata or I/O; treat it as a real operation, not a free property lookup.
- In Polars 2, `collect(engine='auto')` chooses the streaming engine for lazy queries. Eager `DataFrame` work still uses the in-memory engine.
- Streaming is not a promise that every operator uses constant memory or supports every sink/engine combination. Read the installed version's documentation and test the query plan/behavior.

## Row order is a contract, not an accident

Polars 2's streaming execution can produce different row order for joins,
`group_by`, and reshaping operations. If order is observable:

1. Prefer an explicit `.sort(...)` at the output boundary for deterministic ordering.
2. Use `maintain_order=True` only when input-relative ordering itself is required and the cost/engine support is acceptable.
3. Assert output order in tests only when clients or downstream computation depend on it.

Do not compare two frames positionally when row order is intentionally unspecified;
sort by stable keys first.

## Out-of-core behavior

Polars 2 enables spilling for supported operations by default. Memory thresholds
and disk budgets are version/runtime behavior, not an application SLA. Monitor
real workloads and explicitly configure supported resource controls when needed;
never assume every join/group-by will spill successfully.

Source: [Polars 2 release announcement](https://pola.rs/posts/release-polars-2)
and [v2 upgrade guide](https://docs.pola.rs/releases/upgrade/2/).
