---
name: kit-state-data
description: Use when choosing ownership for remote data, cached state, URL state, and transient interface state.
license: MIT
---

# Assign state one clear owner

## Resources

- [Ownership and race guide](references/guide.md): gates, negative sequences,
  recovery.
- [Ownership decision guide](references/ownership-decisions.md): decision tree,
  context versus store, URL rules, smells.
- [Server-state patterns](references/query-patterns.md): key factory,
  `queryOptions`, freshness, pagination, mutations, identity reset.
- [State transition ledger](assets/state-transition-ledger.md) to fill per task.
- Templates: [typed HTTP client](assets/http-client.ts.template) with
  [tests](assets/http-client.test.ts.template),
  [feature API](assets/orders.api.ts.template),
  [keys and query options](assets/orders.queries.ts.template) with
  [tests](assets/orders.queries.test.tsx.template),
  [query client](assets/query-client.ts.template),
  [client-only store](assets/create-store.ts.template) with
  [tests](assets/create-store.test.ts.template).

## Procedure

1. Read the guide; fill the transition ledger before adding any store or effect.
2. Classify each value with the decision tree: derived, server-owned,
   URL-addressable, form draft, shared client, or local interaction state.
3. Use the existing query/cache layer for remote data, not effect-driven mirrors.
4. Define keys through one factory per feature; include every input, never secrets.
5. Parse responses with schemas in the API module; pass `signal` for cancellation.
6. Define freshness, invalidation, pagination, and optimistic recovery per query.
7. Keep form drafts and temporary selections local unless routes truly share them.
8. Represent pending, empty, stale, background-refresh, error, and success
   separately where behavior differs.
9. Prevent old responses and failed optimistic rollbacks from replacing newer
   intent; document the concurrency rule for each optimistic mutation.
10. Scope sensitive caches to authorization boundaries; clear on identity change.
11. Test invalidation, races, refresh, pagination, optimistic failure, and disposal.
12. Report exact commands and results; real API consistency is not proven by mocks.

## Acceptance gates

- [ ] Every value has one recorded owner; no derived value is stored.
- [ ] Query keys come from a factory and include all inputs.
- [ ] Transport errors are typed; client and contract errors are not retried.
- [ ] Each mutation names the keys it updates or invalidates, with a test.
- [ ] Optimistic updates have a rollback test and a concurrency rule.
- [ ] Identity change clears cached private data.
