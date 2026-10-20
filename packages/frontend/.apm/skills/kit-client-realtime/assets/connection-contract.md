# Live connection and recovery contract

- Transport and existing client: {{WebSocket/EventSource/fetch stream, owner}}
- Event schema/version and payload limit: {{contract location, validation seam}}
- Auth boundary and observable terminal signal: {{mechanism; no credentials}}
- Subscription identity and disposal: {{topic/user key, close/unmount/logout}}
- Freshness threshold: {{heartbeat or staleness rule, visible status text}}
- Retry budget: {{attempts/elapsed limit, delay cap, jitter, cancellation}}
- Capacity policy: {{queue/retention bounds, overflow response}}

## Delivery semantics

- Ordering scope and version rule: {{per entity/topic/global or not guaranteed}}
- Deduplication key/window: {{ID, retention bound, replay overlap}}
- Cursor advancement and expiry: {{received/applied boundary per server contract}}
- Snapshot/replay reconciliation: {{watermark/handshake or explicit gap limit}}
- Unsupported guarantees: {{loss, duplication, ordering that cannot be excluded}}

## Sequence acceptance

| Input sequence | Required visible/state result | Test seam and evidence |
| --- | --- | --- |
| Open, disconnect, reconnect | Stale status then synchronized only after recovery | {{result}} |
| New, duplicate, old event | No duplicate or state regression under documented rule | {{result}} |
| Malformed/unknown/oversized event | Policy applied; valid state preserved | {{result}} |
| Expired cursor or gap | Snapshot/resync or explicit failure; no false freshness | {{result}} |
| Burst beyond capacity | Bounded work; configured overflow behavior | {{result}} |
| Dispose or switch user during backoff | No late callback/retry or old private state | {{result}} |
| Terminal failure or retry exhaustion | Retries stop; readable manual recovery | {{result}} |

- Simulated checks and exact command: {{result and test count}}
- Real server/browser evidence, if authorized: {{session or not run}}
- Keyboard/status feedback check: {{retry reachability, announcement behavior}}
- Remaining server guarantees and owner: {{unresolved contracts}}
