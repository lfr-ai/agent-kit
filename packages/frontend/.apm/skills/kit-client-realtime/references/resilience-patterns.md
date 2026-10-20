# Resilience patterns for live clients

## Connection state machine

```text
idle --start--> connecting --open--> open --no traffic--> stale
                    ^                  |                    |
                    |               close (retryable)    message
                    |                  v                    v
             backoff timer <---- reconnecting             open
                                       |
                        budget exhausted or terminal code
                                       v
                                    failed --user retry--> connecting
any state --stop()--> closed
```

Rules the [reconnecting socket](../assets/reconnecting-socket.ts.template)
implements and its tests pin:

- Exactly one socket per owner. A generation counter discards events from sockets
  that were replaced or stopped.
- Backoff uses full jitter (`random() * min(cap, base * 2^attempt)`) so many
  clients do not reconnect in lockstep after a server restart.
- The retry budget is finite. After it is spent the state is `failed` and the user
  gets an explicit retry action.
- Terminal close codes stop retries immediately; retrying an auth rejection only
  adds load.
- `stop()` cancels pending timers and ignores late events; it is the effect
  cleanup.
- Staleness is derived from traffic, not from `readyState`; a heartbeat keeps the
  connection fresh.

## Applying events

The [order events module](../assets/order-events.ts.template) (with
[tests](../assets/order-events.test.ts.template)) shows the pipeline:

1. **Parse**: JSON first, then a discriminated-union schema. Invalid frames are
   counted and dropped; they never reach the cache.
2. **Sequence**: drop duplicates and replays; flag gaps.
3. **Apply**: write through the query cache owner. Compare entity versions or
   timestamps so an older event cannot overwrite newer data.
4. **Resynchronize**: on gaps and after every reconnect, invalidate the affected
   keys so the server's state wins.

Prefer small "entity changed" events plus invalidation over shipping full
documents, unless latency or server load requires direct cache writes.

## React integration

- Create the connection in an effect and stop it in cleanup; Strict Mode's extra
  development setup and cleanup must leave one live socket. See
  [useLiveOrders](../assets/use-live-orders.ts.template).
- Keep callbacks out of effect dependencies (latest-ref pattern, or
  `useEffectEvent` where the installed React version provides it) so a parent
  re-render does not reconnect.
- Mount the live connection at the level that owns the data (route or feature
  root), not in every list row.
- Render status with the [connection banner](../assets/connection-banner.tsx.template):
  a permanently mounted polite live region, text that says whether data may be
  stale, and a retry button. Do not announce every heartbeat.

## Browser lifecycle

| Event | Response |
| --- | --- |
| `offline` | show stale state; skip retries until `online` (optional optimization) |
| `online` | `reconnectNow()` instead of waiting for the backoff timer |
| `visibilitychange` to hidden for a long time | optionally stop and reconnect on visible, then resynchronize |
| `pagehide` / back-forward cache | close sockets so the page stays eligible for bfcache; reconnect on `pageshow` |
| Session expiry | server closes with a terminal code; client signs out or refreshes credentials, then reconnects |

## Capacity limits

- Bound in-memory event buffers; if a consumer falls behind, drop and resync.
- Batch cache writes for bursty streams (for example apply queued events once per
  animation frame) and measure before adding complexity.
- Do not log full payloads; they can contain private data. Log type, sequence,
  and size.

## Anti-patterns

| Anti-pattern | Failure |
| --- | --- |
| `new WebSocket()` in render or without cleanup | duplicate connections, leaks under Strict Mode |
| Fixed one-second reconnect forever | thundering herd and battery drain |
| Retry loop around `EventSource` | doubled connections; fights the browser's own retry |
| Applying events without schema validation | malformed frames crash rendering |
| Trusting push events as the only source of truth | missed events during reconnects are never repaired |
| Token in the stream URL | leaks through logs, history, and referrers |
| Live region that remounts on each status change | screen readers miss announcements |

## Acceptance gates

- [ ] One connection owner with cleanup; Strict Mode development run shows one
      active connection.
- [ ] Tests cover backoff growth and cap, retry budget, terminal codes, stop
      during backoff, stale detection, and late events after stop.
- [ ] Events are validated, deduplicated, ordered by version, and followed by a
      resync after gaps and reconnects.
- [ ] Status is visible and announced politely; the user can retry.
- [ ] Credentials never appear in URLs or logs.
- [ ] Simulated transport evidence is reported separately from a real server run.

## Sources

- MDN, `WebSocket` close event: <https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/close_event>
- MDN, `EventSource.readyState`: <https://developer.mozilla.org/en-US/docs/Web/API/EventSource/readyState>
- MDN, Page Visibility API: <https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API>
- MDN, `online` and `offline` events: <https://developer.mozilla.org/en-US/docs/Web/API/Window/online_event>
- web.dev, back/forward cache: <https://web.dev/articles/bfcache>
- React, separating events from effects: <https://react.dev/learn/separating-events-from-effects>
- WAI-ARIA, `status` role: <https://www.w3.org/TR/wai-aria-1.2/#status>
