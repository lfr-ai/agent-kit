# Schema contracts

A Polars pipeline has an input contract (what sources must contain) and an
output contract (what consumers receive). Make both explicit and check them
before and after expensive work.

## Declare schemas as constants

```python
ORDER_EVENTS = pl.Schema(
    {
        "order_id": pl.Int64,
        "customer_id": pl.Int64,
        "status": pl.Enum(["created", "settled", "refunded"]),
        "amount": pl.Decimal(precision=12, scale=2),
        "occurred_at": pl.Datetime("us", time_zone="UTC"),
    }
)
```

- Use exact dtypes: integer width, `Decimal` for money, timezone-aware
  `Datetime` with a fixed unit, `Enum` for closed categories (`Categorical` only
  when the set is open).
- Keep the schema next to the pipeline that owns it, and version it when
  consumers depend on it.

## Validate before running

`lf.collect_schema()` resolves names and dtypes from source metadata and the
plan without computing the result. Compare against the contract and fail with
every difference at once:

- missing columns,
- unexpected columns (if the contract is closed),
- dtype mismatches.

The [schema contract pattern](../assets/patterns/schema_contract.py.template)
implements `schema_violations()` and `conform()`.

## Conform at ingress

- For CSV and other untyped sources, pass `schema` or `schema_overrides` to the
  scan so parsing produces the right types immediately.
- For typed sources, cast explicitly with `strict=True` (the default) so invalid
  values fail instead of silently becoming null. Use `strict=False` only when
  null-on-failure is the documented behavior, then count the nulls produced.
- Select columns in contract order with `select(schema.names())` so output
  column order is stable.

## Nullability and keys

Polars dtypes do not encode nullability or uniqueness. Check them as data
assertions after collecting the (ideally small) checked subset, or with a lazy
aggregate:

```python
problems = lf.select(
    pl.col("order_id").null_count().alias("null_ids"),
    pl.col("order_id").is_duplicated().sum().alias("duplicate_ids"),
).collect()
```

Fail the pipeline, quarantine bad rows to a separate sink, or report counts,
according to the contract.

## Evolving a schema

- Adding a nullable column is usually compatible for readers that select by name.
- Removing or renaming columns, narrowing dtypes, and changing `Enum` categories
  are breaking; coordinate with consumers.
- Parquet files written under an old schema stay on disk. When scanning mixed
  generations, cast to the current contract explicitly and test with files of
  each generation.

## Sources

- <https://docs.pola.rs/user-guide/lazy/schemas/>
- <https://docs.pola.rs/user-guide/concepts/data-types-and-structures/>
- <https://docs.pola.rs/user-guide/expressions/casting/>
- <https://docs.pola.rs/user-guide/expressions/categorical-data-and-enums/>
- <https://docs.pola.rs/api/python/stable/reference/schema/index.html>
- <https://docs.pola.rs/api/python/stable/reference/lazyframe/api/polars.LazyFrame.collect_schema.html>
