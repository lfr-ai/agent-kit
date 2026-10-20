---
description: Add a live client connection with explicit connection states, schema-validated events, bounded jittered reconnects, cleanup, and visible staleness.
argument-hint: The live data and transport, e.g. "order status over WebSocket"
agent: agent
---

# Add a real-time client connection

Consume live updates in the browser without leaks, duplicate effects, or
silent staleness.

## Input

- The user-supplied argument names the live data and, if known, the
  transport. Ask for the server's ordering, replay, and authentication
  guarantees when the code and docs do not state them.

## Procedure

1. Load [kit-client-realtime](../skills/kit-client-realtime/SKILL.md) and fill
   its connection contract.
2. Choose the transport with the skill's decision guide: server-sent events
   for one-way updates, WebSocket for two-way, polling when updates are rare.
   Reuse an existing connection layer if the project has one.
3. Model connecting, open, stale, reconnecting, closed, and failed as distinct
   states that the UI can render.
4. Validate every received event with a schema; drop and count invalid events
   instead of applying them.
5. Decide per event type whether it is ordered, replayable, deduplicated, or
   safe to miss. Resume from a cursor only when the server guarantees replay.
6. Reconnect with bounded exponential backoff and full jitter; stop on
   authentication or other terminal failures.
7. Open one connection per owner inside an effect and close it in cleanup.
   Bound queued messages so a slow tab cannot grow memory.
8. Merge events into the query cache owned by
   [kit-state-data](../skills/kit-state-data/SKILL.md) rather than a parallel
   store.
9. Keep tokens and private payloads out of URLs, logs, and the console.
10. Show accessible stale and reconnecting feedback without stealing focus.
11. Test with a fake transport: disconnect, reconnect, duplicate event, stale
    cursor, invalid event, cancellation on unmount, and terminal rejection.

## Acceptance gates

- [ ] Unmount and navigation close the connection; tests prove no leak.
- [ ] Reconnect attempts are bounded and jittered.
- [ ] Invalid events never reach UI state.
- [ ] Users can see when data is stale.

## Output

The connection contract, the state diagram as a table, files changed, test
results, and what was proven only against a simulated transport.
