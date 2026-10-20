---
name: kit-client-realtime
description: Use when a browser client consumes WebSocket, event-stream, or other long-lived updates.
license: MIT
---

# Handle a live client connection

## Resources

- [Connection guide](references/guide.md): prerequisites, state and delivery
  gates, negative sequences.
- [Transport decisions](references/transport-decisions.md): polling versus SSE
  versus WebSocket, auth, close codes, browser limits.
- [Resilience patterns](references/resilience-patterns.md): state machine, event
  pipeline, React integration, lifecycle, anti-patterns.
- [Event and recovery contract](assets/connection-contract.md) to fill per stream.
- Templates: [reconnecting socket](assets/reconnecting-socket.ts.template) with
  [tests](assets/reconnecting-socket.test.ts.template),
  [event contract and cache applier](assets/order-events.ts.template) with
  [tests](assets/order-events.test.ts.template),
  [live connection hook](assets/use-live-orders.ts.template),
  [SSE hook](assets/use-event-source.ts.template) with
  [tests](assets/use-event-source.test.ts.template),
  [connection banner](assets/connection-banner.tsx.template).

## Procedure

1. Read the guide; define the protocol in the event and recovery contract.
2. Choose the transport with the decision guide; identify authentication, event
   schema, ordering, replay, heartbeat, server limits, and terminal codes.
3. Model connecting, open, stale, reconnecting, closed, and failed states distinctly.
4. Validate each received event with a schema before applying it to UI state.
5. Define whether events are ordered, replayable, deduplicated, or safe to miss;
   resynchronize through the cache owner after gaps and every reconnect.
6. Reconnect with bounded backoff and full jitter; stop on terminal failures. Do
   not add a retry loop around native `EventSource`.
7. Resume from an explicit cursor only if the server guarantees replay semantics.
8. Create one connection per owner in an effect; stop it in cleanup.
9. Bound queued messages and UI updates so a slow consumer cannot grow memory.
10. Keep tokens and private payloads out of URLs, diagnostics, and console output.
11. Test disconnect, stale cursor, duplicate event, cancellation, and rejection
    paths with fake transports and fake timers.
12. Show accessible stale/retry feedback. Report simulated transport evidence
    separately from a real server session; do not claim durable delivery without
    a protocol guarantee.

## Acceptance gates

- [ ] Transport choice and stream contract are recorded.
- [ ] Reconnection tests cover backoff cap, retry budget, terminal codes, stop
      during backoff, staleness, and late events.
- [ ] Events are schema-validated, deduplicated, version-ordered, and resynced.
- [ ] One connection per owner survives the Strict Mode development cycle.
- [ ] Connection status is visible, politely announced, and retryable.
