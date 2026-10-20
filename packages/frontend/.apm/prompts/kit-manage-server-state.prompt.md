---
description: Assign remote data to the query cache with key factories, schema-parsed responses, freshness, invalidation, and race-safe optimistic updates.
argument-hint: The data or screen to fix, e.g. "invoice list refetch and filters"
agent: agent
---

# Manage server state deliberately

Give every piece of remote data one owner in the query cache, with explicit
freshness, invalidation, and race handling.

## Input

- The user-supplied argument names the data, query, or screen. When it is
  empty, scan the changed frontend files for effect-driven fetching and
  duplicated server state.

## Procedure

1. Load [kit-state-data](../skills/kit-state-data/SKILL.md) and fill its state
   transition ledger before adding any store or effect.
2. Classify each value: derived, server-owned, URL-owned, form draft, or
   transient interface state. Remove copies of server data held in component
   or global state.
3. Use the project's existing query library. Define query keys through one
   factory per feature; include every input and never include secrets.
4. Parse responses with schemas in the feature's API module and pass the abort
   signal for cancellation.
5. Set freshness and garbage-collection times per query from how often the
   data really changes. Document the choice next to the query.
6. After each mutation, invalidate or update exactly the affected keys. For
   optimistic updates, snapshot, apply, and roll back on failure without
   overwriting newer data.
7. Represent pending, empty, stale, background refresh, error, and success
   distinctly in the UI.
8. Scope caches holding user-specific data to the identity and clear them on
   sign-out or account switch.
9. Write tests for invalidation, out-of-order responses, refresh, pagination,
   optimistic failure, and identity change.
10. Run type, lint, and test commands.

## Acceptance gates

- [ ] No effect copies server data into local or global state.
- [ ] Each mutation names the keys it invalidates, with a test.
- [ ] An older response never replaces newer data.
- [ ] User-scoped caches clear on identity change.

## Output

The ledger as a table (value, owner, key, freshness, invalidated by), files
changed, commands run with results, and consistency assumptions that mocks
cannot prove against the real API.
