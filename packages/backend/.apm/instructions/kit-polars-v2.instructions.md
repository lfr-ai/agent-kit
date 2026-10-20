---
description: Apply to likely Polars pipeline and analytics modules.
applyTo: "**/*polars*.py,**/*dataframe*.py,**/*analytics*.py"
---

- When using Polars 2, prefer composable expressions and lazy scans; make observable ordering, schema, casts, null semantics, and engine behavior explicit.
- Start pipelines with `scan_*` and call `collect` once at the boundary; avoid eager reads followed by filtering.
- Declare input schemas and cast explicitly; do not rely on inference for columns that cross a boundary.
- Do not assume grouping, `unique`, or joins preserve row order; sort explicitly when order is observable.
- Express transformations as expressions; avoid Python UDFs and row iteration unless no expression exists, and document why.
- Keep Polars frames at a data-processing boundary; do not make domain Core depend on Polars.
- Compare frames in tests with `polars.testing.assert_frame_equal` on small synthetic inputs.
- Read the consumer lockfile and `kit-polars-v2` upgrade guide before changing streaming, ordering, concat, or schema behavior.

See the [Polars 2 procedure](../skills/kit-polars-v2/SKILL.md).
