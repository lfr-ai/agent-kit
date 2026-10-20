# Polars 1-to-2 migration checklist

Use the complete official upgrade guide for the consumer's exact release. The
changes below are high-impact checks, not an exhaustive substitute for it.

| v2 behavior | Review |
| --- | --- |
| Lazy `collect(engine='auto')` defaults to streaming | Recheck row-order assumptions and streaming operator support |
| Out-of-core spilling enabled by default | Review disk-budget and resource expectations |
| `LazyFrame.profile()` removed | Choose a profiling facility supported by the installed release |
| `pl.concat` / `pl.union` stricter | Test dtype mismatches and select coercion explicitly |
| `explode()` defaults `empty_as_null=False` | Check empty-list semantics |
| Integer supertype changes include `Int128` | Recheck downstream schemas, casts, database/JSON serialization |
| `is_in()` coercion is stricter | Make compatible casts explicit |
| CSV schema overrides and column selection semantics changed | Recheck complete schema overrides and requested output order |
| Arrow `Map` has a native Polars dtype | Recheck assumptions that Arrow maps arrive as list-of-struct |

After migration, compare schemas as well as values and include null/empty/order
cases in the regression set. Do not bulk-rename deprecated methods without
reviewing changed semantics. [check_polars_usage.py](../assets/check_polars_usage.py)
lists renamed APIs and the deprecated `collect(streaming=...)` flag as a starting
inventory.

Source: [official Polars 2 upgrade guide](https://docs.pola.rs/releases/upgrade/2/).
