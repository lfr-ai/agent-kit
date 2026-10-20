# Browser connection and event recovery

## Verification prerequisites

- Confirm the existing transport: WebSocket, native EventSource, or a fetch-based
  stream. Record server event schema/version, auth/session mechanism, limits,
  cursor lifetime, ordering scope, and replay guarantees. Unknown guarantees stay
  unknown; do not invent durable delivery or exactly-once processing.
- Inspect browser API limitations. Native EventSource has built-in reconnection;
  adding a second retry loop can create duplicate connections. Neither browser
  WebSocket nor native EventSource accepts arbitrary auth headers like fetch.
- Identify one connection owner, disposal point, synthetic event harness, and
  supported environments. A mocked stream cannot establish server interoperability.

## State and delivery quality gates

| State or boundary | Required contract |
| --- | --- |
| Connecting/open | One active subscription per intended owner; transport-open and application-synchronized are distinct when replay/snapshot is pending. |
| Stale | Freshness has a defined threshold or heartbeat contract; UI labels old data and does not claim it is current. |
| Reconnecting | Attempts, elapsed retry budget, delay cap and jitter are bounded and testable; explicit close/unmount cancels pending retry. |
| Failed/closed | User-requested close stays closed; terminal auth/protocol failures stop when observable and offer a safe next action. |
| Event boundary | Check type, schema/version and payload bounds before mutation; malformed/unknown events follow an explicit drop, resync or failure policy. |
| Ordering | Deduplication key and ordering scope are documented; a newer entity version cannot be replaced by an older event. |
| Capacity | Bound retained events and queued rendering work; exceeding a limit triggers the documented resync/drop/close policy, not unbounded growth. |

Browser error callbacks often hide HTTP handshake status. Do not assume a
WebSocket error or EventSource `error` identifies a 401. Stop on explicit protocol
signals, known session expiry, or the retry budget; describe ambiguous failures.
Do not wrap native EventSource reconnection with an independent timer; close it
when the lifecycle/retry budget requires termination.

## Negative event sequences

- Apply event `v2`, duplicate `v2`, then older `v1`: do not duplicate a row or
  regress the entity. If the protocol lacks versions, use its documented resync
  strategy rather than asserting an ordering guarantee.
- Disconnect after receiving but before applying an event; reconnect with a
  valid cursor. Advance the applied cursor only according to the protocol's
  processing contract.
- Supply an expired cursor or an unreplayable gap. Fetch a fresh snapshot and
  reconcile under a server-defined watermark/handshake; otherwise acknowledge a
  possible gap instead of silently calling the stream synchronized.
- Receive malformed JSON, unknown event type, oversized payload, or a burst
  faster than rendering. Preserve UI integrity and exercise the capacity policy.
- Unmount, change topic, log out, or switch user during backoff. Old callbacks,
  credentials, queues and user-specific data must not reach the new view.

## Recovery and verification

1. Represent stale/reconnecting status in text, with restrained status
   announcements; do not move focus on each reconnect or rely on a colored dot.
2. For retry exhaustion, offer a deliberate retry or snapshot refresh. Resume
   automatically only where the protocol permits it; mutations need independent
   acknowledgment/idempotency rules.
3. Test timers, randomness, event ordering and disposal with the installed test
   harness. Assert no active listener/retry remains after owner disposal.
4. If authorized infrastructure exists, exercise disconnect/reconnect against it
   and record protocol evidence separately. Do not start a service implicitly.
5. Complete the [connection contract](../assets/connection-contract.md) and retain
   unresolved auth/replay guarantees as limits, not manufactured test results.

## Primary official sources

- WebSocket browser API and lifecycle: <https://websockets.spec.whatwg.org/>
- EventSource and reconnection semantics: <https://html.spec.whatwg.org/multipage/server-sent-events.html>
- Browser stream handling: <https://streams.spec.whatwg.org/>
