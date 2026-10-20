# Debt ledger

A simplification often means choosing a smaller solution that is good enough
today and knowingly limited. That is healthy when the limit is written down
where the code lives and someone owns the revisit decision. The ledger turns
those comments into a reviewable list.

## Marker convention

Write a comment, in the file's own comment syntax, with a marker keyword,
optional metadata in parentheses, a colon and a reason:

```python
# DEBT(owner=@orders-team, revisit=2026-09-30): cache is per-process; replace with a shared cache before running more than one instance
```

```typescript
// SHORTCUT(owner=@web-team, revisit=when exports exceed 10k rows): builds the CSV in memory
```

```sql
-- DEBT(owner=@data-team): no index on created_at yet; nightly report is the only reader
```

Rules:

- **Marker**: `DEBT` for a known limitation with a cost that grows, `SHORTCUT`
  for a deliberate scope cut that is fine until a trigger. Projects may add
  their own with `--marker`; keep the set small.
- **Reason** (required): what is limited and why it is acceptable now. Write
  it for the person who will hit the limit.
- **owner** (recommended; required with `--require-owner`): a team or role
  handle, not a personal name, so the entry survives staffing changes.
- **revisit** (recommended): an ISO date (`YYYY-MM-DD`) or a trigger condition
  ("when a second tenant is onboarded"). Dates are checked with `--as-of`;
  triggers are reviewed by people.
- One marker per limitation, placed on the line closest to the limited code.
- Do not use markers for bugs. A known defect belongs in the issue tracker,
  with the marker linking to it only if the code intentionally works around it.

## Collector

[collect_debt_markers.py](../assets/collect_debt_markers.py) scans explicit
paths without importing or executing anything:

```text
python assets/collect_debt_markers.py src --output docs/debt-ledger.md
python assets/collect_debt_markers.py src --as-of 2026-06-01 --require-owner
python assets/collect_debt_markers.py . --marker DEBT --marker COMPAT --ext .py --ext .ts
python assets/collect_debt_markers.py infra --all-files --exclude "*.generated.*"
```

Behavior:

- A marker matches only after a comment leader (`#`, `//`, `/*`, `*`, `--`,
  `<!--`, `;`, `%`, `REM`) and as a whole word, so identifiers like
  `DEBT_LIMIT` are ignored.
- Directory scans skip version-control, virtual-environment, dependency and
  build folders by default; `--exclude` replaces that list with your globs,
  matched against each relative path part.
- Output is a Markdown table sorted by path and line, with per-marker counts.
- Findings go to standard error as `path:line: message` and set exit status 1:
  missing reason, missing owner (with `--require-owner`), invalid date, or a
  revisit date before `--as-of`.
- Pass `--as-of` explicitly in CI (for example the pipeline's run date) so the
  result is reproducible for a given input.

## Review workflow

1. During a simplification review, add a marker for every deliberate limit you
   introduce or accept, in the same diff.
2. Regenerate the ledger and include its diff in the review; reviewers check
   that each new entry has a real reason, an owner and a revisit.
3. On a regular cadence (each release or each quarter), run the collector with
   `--as-of` set to the review date. For each expired entry, the owner either
   pays the debt, sets a new date with a reason, or deletes the marker because
   the limit no longer matters.
4. Track the total count over time. A rising count is fine if entries are being
   resolved; a growing set of expired entries is the warning sign.

## Anti-patterns

- Markers without reasons ("DEBT: fix later"); the collector rejects them.
- Personal names as owners; use team or role handles.
- Ledgers committed but never regenerated; generate in CI or at review time.
- Using the ledger as a backlog of features; it records limits of existing
  code, not wishes.

## Sources

- [Python re module](https://docs.python.org/3/library/re.html)
- [Python fnmatch module](https://docs.python.org/3/library/fnmatch.html)
- [Python datetime.date.fromisoformat](https://docs.python.org/3/library/datetime.html#datetime.date.fromisoformat)
- [GitHub Flavored Markdown tables](https://github.github.com/gfm/#tables-extension-)
