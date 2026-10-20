# Pagination

Every collection endpoint that can grow must be paginated from its first
release; adding pagination later is a breaking change.

## Styles

| Style | Request | Strengths | Weaknesses |
| --- | --- | --- | --- |
| Cursor (keyset) | `?limit=50&cursor=opaque` | Stable under inserts and deletes; fast on large tables | No random page access; total count is extra work |
| Offset | `?limit=50&offset=100` | Simple; random access | Skips or repeats items when data changes; slow deep pages |
| Page number | `?page=3&page_size=50` | Familiar in UIs | Same problems as offset |

Default to cursor pagination for APIs; use offset only for small, mostly static
collections.

## Cursor rules

- The cursor is opaque to clients: encode the last sort key and tie-breaker
  (for example `created_at` plus `id`) and base64url-encode it. Sign or encrypt
  it if it must not be tampered with.
- Sort by a deterministic key with a unique tie-breaker; otherwise items can be
  skipped or duplicated between pages.
- Bind the cursor to the filter and sort parameters; reject a cursor reused with
  different parameters (400 with a problem details body).
- Cursors may expire; document the lifetime and return 400 for an expired cursor.

## Response shape

```json
{
  "items": [{"id": "ord-1"}, {"id": "ord-2"}],
  "next_cursor": "eyJjIjoiMjAyNi0wMS0wMlQxMDowMDowMFoiLCJpIjoib3JkLTIifQ",
  "has_more": true
}
```

Optionally add an RFC 8288 `Link` header with `rel="next"`. Return
`next_cursor: null` and `has_more: false` on the last page.

## Limits

- Define a default `limit` and a documented maximum. Clamp or reject (400)
  larger values consistently; document which.
- Validate `limit` as a positive integer.
- Avoid returning total counts by default on large collections; offer them
  through an explicit parameter if needed.

## Compatibility

- Changing the default or maximum page size, sort order, or cursor format is a
  contract change; announce it and keep old cursors working through a
  transition period.
- Clients must treat the cursor as opaque and must follow `next_cursor` until it
  is null.

## Tests

- First page, middle page, last page, and empty collection.
- Concurrent insert between page requests does not cause duplicates or gaps for
  existing items.
- Invalid, tampered, mismatched, and over-limit inputs return problem details.

## Sources

- [RFC 8288 - Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [RFC 4648 - Base64url encoding](https://www.rfc-editor.org/rfc/rfc4648.html#section-5)
- [Google AIP-158 - Pagination](https://google.aip.dev/158)
- [Microsoft REST API guidelines: collections](https://github.com/microsoft/api-guidelines/blob/vNext/azure/Guidelines.md)
