# State ownership decision guide

Every value in the interface has exactly one owner. Pick it with the questions
below, in order; stop at the first "yes".

## Decision tree

1. **Can it be computed from other state or props?** Derive it during render.
   Examples: filtered rows, totals, "has unsaved changes" from draft versus saved.
2. **Does the server own the truth?** Server cache (query layer or route loader).
   Examples: orders, invoices, the signed-in user's profile.
3. **Should a link, reload, or back button restore it?** URL (path or search
   params) through the router. Examples: selected tab, filters, page, sort, the
   open record id.
4. **Is it an unsaved edit?** Form state owned by the form component or form
   library, initialized from server data and keyed by entity id.
5. **Do distant components on the same screen need it, and is it not shareable
   by URL?** Shared client store or context. Examples: bulk selection, panel
   layout, a command palette's open state.
6. **Otherwise** it is local component state. Examples: hover, disclosure open,
   input focus, a transient animation flag.

Persisted preferences (theme, density) belong to a small store backed by
`localStorage` with a schema check on read; never persist server data or tokens
there by default.

## Owner comparison

| Owner | Survives reload | Shareable link | Cross-tab | Typical tool |
| --- | --- | --- | --- | --- |
| Derived | n/a | n/a | n/a | plain expressions, `select` |
| Server cache | refetched | via URL inputs | refetch on focus | query library, loaders |
| URL | yes | yes | no | router search params |
| Form draft | no (unless persisted deliberately) | no | no | form library, `useActionState` |
| Shared client store | no | no | no | external store, context |
| Local state | no | no | no | `useState`, `useReducer` |

## Context versus store

- Context fits values that change rarely and are read widely: theme, locale,
  current identity, injected services.
- An external store with selectors fits values that change often and are read
  by a few components; consumers re-render only when their slice changes.
- Put a stable object (services, dispatch) in context, not a frequently changing
  value with many consumers.

## URL state rules

- Parse search params with a schema; invalid values fall back to defaults instead
  of crashing.
- Write with `replace` for typing in a filter box, `push` for deliberate
  navigation steps.
- Omit default values from the URL so links stay short and canonical.
- Never put personal or secret data in the URL; it lands in logs and history.

## Ownership smells

| Smell | Usually means |
| --- | --- |
| `useEffect` that copies one state into another | a derived value or wrong owner |
| The same id stored in URL and a store | two owners; pick the URL |
| A store holding fetched entities | server state outside the cache |
| Form fields reset after background refetch | draft owned by the query, not the form |
| Context value object recreated every render | unnecessary re-renders of all consumers |
| Prop drilled through five layers unchanged | composition (children) or context |

Record each decision in the [state transition ledger](../assets/state-transition-ledger.md);
use the [query patterns](query-patterns.md) for server-owned values.

## Acceptance gates

- [ ] Each new value has a recorded owner, reset rule, and invalidation path.
- [ ] No value is stored in two owners; derived values are not stored at all.
- [ ] URL-owned values survive reload and back/forward in a test.
- [ ] Drafts survive background refetch and reset on entity change.
- [ ] Persisted client state is schema-checked on read and scoped by identity.

## Sources

- React, choosing the state structure: <https://react.dev/learn/choosing-the-state-structure>
- React, sharing state between components: <https://react.dev/learn/sharing-state-between-components>
- React, passing data deeply with context: <https://react.dev/learn/passing-data-deeply-with-context>
- React, `useSyncExternalStore`: <https://react.dev/reference/react/useSyncExternalStore>
- MDN, `URLSearchParams`: <https://developer.mozilla.org/en-US/docs/Web/API/URLSearchParams>
- MDN, Web Storage API: <https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API>
