---
name: kit-server-streaming
description: Use when designing server-to-client streaming with bounded resources, cancellation, and clear partial-result semantics.
license: MIT
---

# Stream with explicit lifecycle semantics

## Procedure

1. Select the transport from the direction of data, client platforms, and
   infrastructure; prefer SSE for server-to-browser updates
   ([transport-selection.md](references/transport-selection.md)).
2. Write the stream contract: event names, payload fields, contiguous
   sequence ids, and exactly one terminal `end` event with a status
   ([sse-protocol.md](references/sse-protocol.md),
   [stream_events.py.template](assets/stream_events.py.template)).
3. Confirm proxy, load balancer, CDN, server and client timeout, buffering and
   compression behavior for the deployed route
   ([proxies-and-timeouts.md](references/proxies-and-timeouts.md)).
4. Authenticate and authorize before the first byte; avoid secrets in query
   strings; re-check on every reconnect and bound connection lifetime.
5. Send only validated, typed events with stable names; clients ignore
   unknown names so the contract can grow compatibly.
6. Decouple producers from connections through a hub with bounded replay,
   per-subscriber queues, event size, stream and subscriber limits
   ([event_hub.py.template](assets/event_hub.py.template)).
7. Choose a backpressure policy per feature and propagate client disconnect
   and explicit cancellation to upstream work
   ([backpressure-and-cancellation.md](references/backpressure-and-cancellation.md)).
8. Define reconnect behavior: resume after `Last-Event-ID`, 409 when replay
   is impossible, 204 when the stream already ended.
9. Send heartbeats below the smallest idle timeout and disable intermediary
   buffering ([sse_endpoint.py.template](assets/sse_endpoint.py.template)).
10. Distinguish completion, failure, cancellation, timeout and transport close
    in client behavior; never present a partial stream as complete unless
    `end` says `completed`.
11. Log safe lifecycle metadata and failure categories, never full content.
12. Test from the client side: statuses before streaming, headers, framing,
    resume, slow consumers, disconnect, producer timeout and failure, cancel,
    and empty completion ([references/guide.md](references/guide.md)).
13. Validate recorded streams against the contract with
    [verify_stream_events.py](assets/verify_stream_events.py), using
    [stream_template.json.template](assets/stream_template.json.template) as
    the reference shape.

## Acceptance gates

- Event schema documented; exactly one terminal `end` with a status value.
- Authorization happens before streaming; failures are HTTP statuses.
- Resume via `Last-Event-ID` has no gaps or duplicates and is tested.
- Every buffer, queue, event, stream count and connection lifetime is bounded.
- Cancellation and disconnect reach upstream work as specified.
- Heartbeats and buffering are verified on the deployed path.

## Failure modes

- Missing terminal markers producing streams that never end.
- Partial output accepted as a complete result.
- Buffering proxies, compression, or idle timeouts breaking delivery.
- Unbounded per-connection memory under slow consumers.
