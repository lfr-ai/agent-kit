# Lazy execution, streaming, and sinks

## Shape of a lazy pipeline

1. **Scan** sources with `pl.scan_parquet`, `pl.scan_csv`, `pl.scan_ipc`, or
   `pl.scan_ndjson`. Globs and hive-partitioned directories
   (`hive_partitioning=True`) are scanned as one frame; cloud URLs take
   `storage_options` from configuration, never from literals.
2. **Transform** with expressions on the `LazyFrame`. Each step only extends the
   query plan.
3. **Validate the plan schema** with `collect_schema()` before running expensive
   work; see [schema contracts](schema-contracts.md).
4. **Materialize once** at the boundary: `collect()` for small results that the
   caller needs in memory, or a sink for large outputs.

Avoid `collect()` in the middle of a pipeline followed by `.lazy()`; it discards
optimization across the boundary and holds the intermediate result in memory.
The [usage checker](../assets/check_polars_usage.py) reports this and eager
`read_*` calls followed by `.lazy()`.

## What the optimizer does

- **Projection pushdown** reads only columns the plan uses. Selecting columns
  early is still good documentation, but the optimizer does it anyway.
- **Predicate pushdown** moves filters into the scan, which with Parquet row
  group statistics can skip whole row groups.
- **Slice pushdown**, common subplan elimination, and expression simplification
  reduce work further.

Inspect the optimized plan with `lf.explain()`; compare with
`lf.explain(optimized=False)` when a filter does not seem to reach the scan.
Python UDFs (`map_elements`, `map_batches`) and some operations block pushdown
past them, so place filters before them.

## Streaming and memory

- In Polars 2, `collect()` uses the streaming engine by default for lazy
  queries; see [Polars 2 execution](v2-execution.md). Streaming processes data
  in batches and can handle inputs larger than memory for supported operations.
- Operations that need all data (some sorts, certain joins, pivots) may still
  buffer large state or spill to disk. Test with production-sized inputs and
  watch memory and disk.
- Prefer sinks for large outputs:

  ```python
  (
      pl.scan_parquet(source)
      .filter(pl.col("status") == "settled")
      .group_by("customer_id")
      .agg(pl.col("amount").sum().alias("settled_amount"))
      .sort("customer_id")
      .sink_parquet(target)
  )
  ```

  `sink_parquet`, `sink_csv`, `sink_ipc`, and `sink_ndjson` stream results to
  storage without building a full in-memory frame.

## Multiple outputs from one source

- `pl.collect_all([lf_a, lf_b])` executes several lazy frames together and
  shares common subplans, so a source is scanned once.
- `lf.cache()` marks a subplan for reuse within one query; use it only when the
  plan reuses the same expensive branch.

## Eager is fine when

- Data is already in memory and small (unit tests, request-scoped data).
- An operation exists only on `DataFrame` (some reshapes, interop calls).
- Interactive exploration, where immediate feedback matters more than
  optimization.

Keep the eager section as small as possible and convert back with `.lazy()`
only if more transformations follow and the data is small.

## Interop boundaries

- `to_arrow()` is zero-copy for most types; `to_pandas()` converts and can be
  expensive. Convert once at the edge of the module that needs another library.
- `to_dicts()` and `rows()` create Python objects per value; use them only for
  small results crossing into domain code.

## Sources

- <https://docs.pola.rs/user-guide/lazy/using/>
- <https://docs.pola.rs/user-guide/lazy/optimizations/>
- <https://docs.pola.rs/user-guide/lazy/query-plan/>
- <https://docs.pola.rs/user-guide/concepts/streaming/>
- <https://docs.pola.rs/user-guide/io/hive/>
- <https://docs.pola.rs/user-guide/io/cloud-storage/>
- <https://docs.pola.rs/api/python/stable/reference/api/polars.collect_all.html>
- <https://docs.pola.rs/api/python/stable/reference/api/polars.LazyFrame.sink_parquet.html>
