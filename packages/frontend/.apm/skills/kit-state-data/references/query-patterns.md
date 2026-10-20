# Server-state patterns with a query cache

These patterns assume TanStack Query v5 in a React project. Confirm the installed
major version before copying; v4 differs in option names (`cacheTime`, `isLoading`
semantics, callback options on `useQuery`).

## Building blocks

| Piece | Template | Responsibility |
| --- | --- | --- |
| HTTP client | [http-client.ts](../assets/http-client.ts.template), [tests](../assets/http-client.test.ts.template) | URL building, auth header, timeout plus caller abort, problem-details errors, schema parsing |
| Feature API | [orders.api.ts](../assets/orders.api.ts.template) | one function per endpoint; passes `signal`; returns validated domain types |
| Keys and options | [orders.queries.ts](../assets/orders.queries.ts.template), [tests](../assets/orders.queries.test.tsx.template) | key factory, `queryOptions`, `infiniteQueryOptions`, mutation hook |
| Client | [query-client.ts](../assets/query-client.ts.template) | retry policy, freshness defaults, global error hooks, identity reset |
| Client-only store | [create-store.ts](../assets/create-store.ts.template), [tests](../assets/create-store.test.ts.template) | shared UI state without a library, via `useSyncExternalStore` |

## Query key factory rules

1. Keys are arrays, most general first: `["orders"]`, `["orders", "list", filters]`,
   `["orders", "detail", id]`.
2. Everything the query function reads goes into the key: filters, page cursor
   scope, locale if the server localizes, tenant or account id when one client
   instance spans scopes. Secrets and tokens never go into keys.
3. Normalize inputs (trim, drop empty values) so equivalent requests share a cache
   entry. Object key order does not matter; values do.
4. Nest so that one prefix invalidation reaches every dependent entry: all list
   variants live under `["orders", "list"]`.
5. Export the factory from the feature's public index so other features invalidate
   through it instead of retyping literals.

## `queryOptions` as the single definition

Define key, function, and freshness together and reuse the result everywhere:

```ts
useQuery(ordersQueries.detail(id));                    // component
await queryClient.ensureQueryData(ordersQueries.detail(id)); // route loader
queryClient.setQueryData(ordersQueries.detail(id).queryKey, order); // typed cache write
```

Per-call overrides (`select`, `enabled`) spread on top: `{ ...ordersQueries.list(f), select: pickTotals }`.
`select` derives a view without storing a second copy.

## Freshness and refetch

| Setting | Meaning | Typical choice |
| --- | --- | --- |
| `staleTime` | how long data counts as fresh (no background refetch) | 30 s for lists, longer for reference data, `Infinity` for immutable records |
| `gcTime` | how long unused entries stay in memory | default 5 min; shorter for sensitive data |
| `refetchOnWindowFocus` | refresh stale data when the tab regains focus | on for collaborative data |
| `placeholderData: keepPreviousData` | keep the previous result while new params load | filters and pagination |
| `retry` | attempts for failed reads | transient failures only; see `shouldRetry` |

Status fields are distinct; render them deliberately:

- `isPending`: no data yet. Show a skeleton or status text.
- `isError` with no data: page-level error with retry.
- `isError` with data: keep data, show a non-blocking stale or error notice.
- `isFetching` with data: background refresh; set `aria-busy`, keep content.
- `isPlaceholderData`: data belongs to previous params; dim or label it and do not
  allow actions that assume it matches the new filter.

## Pagination

- Cursor pagination: `infiniteQueryOptions` with `initialPageParam` and
  `getNextPageParam`; the key includes normalized filters so a filter change starts
  a new list instead of appending to the old one.
- Offset pagination: page number in the key with `keepPreviousData`; prefetch the
  next page with `queryClient.prefetchQuery` when the user is likely to continue.
- Render "Load more" as a button with a live status for appended counts; infinite
  scroll needs a keyboard-reachable alternative.

## Mutations

Choose the update strategy by risk:

| Strategy | When | Cost |
| --- | --- | --- |
| Invalidate after success | default; server is the source of truth | one extra request |
| Write response into cache (`setQueryData`) then invalidate lists | server returns the updated entity | lists still refetch |
| Optimistic cache update with rollback | latency matters and conflicts are rare | rollback logic, concurrency rules |
| Optimistic UI via `variables` of a pending mutation | display-only feedback for one place | no cache writes to undo |

The template's optimistic hook snapshots the previous value. That rollback is
safe only while one mutation per entity is in flight: disable the control while
`isPending`, or give mutations a `mutationKey` and check `useIsMutating` before
starting another. With concurrent edits, invalidate instead of restoring a
snapshot, so a later confirmed change is not erased.

Always `cancelQueries` for the affected key before writing optimistically; an
in-flight read would otherwise overwrite the optimistic value.

## Identity and retention

- On sign-out or account switch call `resetForIdentityChange`: cancel in-flight
  queries, then `clear()`. Removing only some keys leaks private data into the next
  session.
- If the project persists the cache, scope the storage key per identity, set a
  `maxAge`, and exclude sensitive queries via `dehydrate` options.

## Anti-patterns

| Anti-pattern | Consequence | Replacement |
| --- | --- | --- |
| Copying `data` into `useState` | stale copy after refetch or mutation | read the query; derive with `select` |
| String keys like `"orders-" + id` | prefix invalidation impossible | array keys from the factory |
| Filters missing from the key | cached results shown for the wrong filter | include every input |
| `refetch()` after mutation in a component | other views stay stale | `invalidateQueries` by prefix |
| `enabled: false` plus manual `refetch` for forms | loses caching semantics | `useMutation` for writes, `fetchQuery` for one-off reads |
| Retrying 4xx and schema errors | slow failures, repeated side effects | `shouldRetry` by error type |
| Global spinner on any `isFetching` | flashing UI, lost context | local `aria-busy` and stale notices |
| New `QueryClient` per render | cache wiped on every render | create once at the app root (and once per test) |

## Acceptance gates

- [ ] Every query uses a key from the feature factory that includes all inputs.
- [ ] Reads pass `signal`; responses are schema-parsed; 4xx and shape errors are
      not retried.
- [ ] Each mutation names the keys it invalidates or updates; a test proves lists
      and details reconcile.
- [ ] Optimistic updates have a rollback test and a documented concurrency rule.
- [ ] Identity change clears the cache in a test or a reviewed code path.

## Sources

- TanStack Query, query keys: <https://tanstack.com/query/latest/docs/framework/react/guides/query-keys>
- TanStack Query, query options: <https://tanstack.com/query/latest/docs/framework/react/guides/query-options>
- TanStack Query, important defaults: <https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults>
- TanStack Query, optimistic updates: <https://tanstack.com/query/latest/docs/framework/react/guides/optimistic-updates>
- TanStack Query, infinite queries: <https://tanstack.com/query/latest/docs/framework/react/guides/infinite-queries>
- TanStack Query, query cancellation: <https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation>
- TanStack Query, testing: <https://tanstack.com/query/latest/docs/framework/react/guides/testing>
- RFC 9457 problem details: <https://www.rfc-editor.org/rfc/rfc9457.html>
- MDN, `AbortSignal.any`: <https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/any_static>
- React, `useSyncExternalStore`: <https://react.dev/reference/react/useSyncExternalStore>
- Mock Service Worker: <https://mswjs.io/docs/>
