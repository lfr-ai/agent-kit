# State ownership and transition ledger

- Changed user task and installed data layer: {{task, cache/store/router}}
- API assumptions: {{pagination, identity/version, mutation/idempotency contract}}
- Synthetic fixture and response control: {{setup/reset, deferred requests}}

## Ownership map

| Value | Authoritative owner | Key/scope | Freshness/reset rule | Derived instead of stored? |
| --- | --- | --- | --- | --- |
| {{remote collection/entity}} | {{cache/loader}} | {{filters/page/auth context, no secrets}} | {{stale/eviction}} | {{yes/no}} |
| {{URL selection}} | {{router}} | {{query/path}} | {{history/canonicalization}} | {{yes/no}} |
| {{draft/temporary value}} | {{local owner}} | {{entity/revision}} | {{explicit reset}} | {{yes/no}} |

## Transition gates

| Sequence | Allowed final state | Forbidden outcome | Evidence |
| --- | --- | --- | --- |
| A starts; B starts; B resolves; A resolves/rejects | B content/status | Old A replaces new intent | {{result}} |
| Page pending; filter changes; old page resolves | New query only | Append records/cursor from old filter | {{result}} |
| Mutation confirmed; visit list/detail/aggregate | All affected views reconcile | Stale contradictory view | {{result}} |
| M1 optimistic; M2 confirmed; M1 fails | M2 retained or authoritative refetch | Snapshot rollback erases M2 | {{result}} |
| Refresh fails with usable cached data | Stale data plus readable retry/error | False empty or lost draft | {{result}} |
| Identity changes during pending work | New scope only, old cache evicted | Private cross-scope data | {{result}} |
| Owner disposed before completion | No late UI/focus update | Abandoned work mutates view | {{result}} |

- Invalidation set and optimistic fallback: {{keys, version rule/refetch}}
- Status/focus/keyboard behavior: {{feedback and recovery}}
- Exact focused checks: {{commands and results}}
- Persistence cleanup and runtime limits: {{verified scope or not run}}
