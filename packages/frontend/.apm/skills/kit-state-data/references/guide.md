# State ownership, freshness and racing work

## Verification prerequisites

- Inventory server data, URL state, local drafts, shared interaction state and
  derived values. Identify existing query/store/router owners and versions.
- Confirm API pagination, mutation response, entity identity/version, auth scope
  and idempotency rules. Do not infer these from a cache library's defaults.
- Use synthetic data and controllable response completion in the installed
  harness. A passing mocked race does not establish real API consistency.

## Ownership quality gates

| Value or operation | Required decision |
| --- | --- |
| Remote data | Existing cache/loader owns it; keys include relevant resource, filters, pagination and authorization context without containing secrets. |
| URL state | Router owns shareable selection/filter values; local mirrors cannot write history loops. |
| Draft/temporary selection | Local owner and explicit reset policy; background refetch does not silently erase edits. |
| Derived value | Compute from current sources unless a measured requirement justifies stored state and its invalidation. |
| Freshness | Define when stale data may remain visible, when it blocks actions, and how users recognize refetching or failure. |
| Mutation | Define affected detail/list/aggregate keys and update/invalidate them after confirmed server outcome. |
| Optimistic update | Apply only with a reconciliation/rollback rule that cannot overwrite a later successful mutation. |
| Retention | Evict private data on identity/authorization change and under the consumer's retention policy, including persisted storage if used. |

Cancellation and ordering are separate concerns. Aborting a fetch may save work,
but a response already completed or a noncancelable promise can still settle.
Use the existing query ownership or request-generation contract so only current
work updates the relevant view.

## Negative sequences and failure modes

1. Request A for input A, then request B for B; resolve B before A. B must remain
   displayed and an A error must not replace B's status.
2. Load page 2, change filters, then resolve the old page. Do not append old-query
   records or reuse a cursor under new filters.
3. Mutate a detail record, then revisit its filtered list and aggregate. Check all
   affected views rather than merely the page that initiated the mutation.
4. Optimistically apply M1, apply and confirm M2, then reject M1. A blanket
   snapshot restore would erase M2; reconcile by version/operation or refetch the
   authoritative state using the existing contract.
5. Background refresh fails while usable data exists. Show stale/error feedback
   without pretending the collection is empty or discarding the draft.
6. Switch account or tenant while pending or after persistence. Old results and
   cached private data must not become visible in the new scope.
7. Navigate away then return. Decide whether reuse is fresh enough; do not assume
   a mounted component or completed network request implies current data.

## Recovery and verification

- Complete the [transition ledger](../assets/state-transition-ledger.md) before
  adding a new store/effect. Prefer existing owners over parallel state systems.
- For uncertain mutation outcomes, reconcile with server identity/version or
  operation status where supported. Do not blindly replay non-idempotent work.
- If concurrent optimistic operations lack a safe rollback protocol, use
  pessimistic confirmation or invalidate/refetch rather than a fragile snapshot.
- Present stale/retry/error status in text with restrained announcements and
  keyboard-reachable actions. Preserve focus and edits during background updates.
- Test out-of-order completion, invalidation, optimistic rejection, pagination,
  identity change and owner disposal with controlled fixtures.
- Run focused integration/component checks and record real API/browser checks
  separately. Review persistence cleanup directly if the project persists caches.

## Primary official sources

- React state structure, when applicable: <https://react.dev/learn/choosing-the-state-structure>
- AbortController cancellation contract: <https://dom.spec.whatwg.org/#interface-abortcontroller>
- HTTP caching and invalidation: <https://www.rfc-editor.org/rfc/rfc9111.html>
- URL state parsing: <https://url.spec.whatwg.org/>
