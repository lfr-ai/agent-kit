# Backpressure and cancellation

A stream couples a producer (for example a model generating tokens) to a
consumer on the other side of a network. If either side is slower or goes
away, resources accumulate unless the design says what happens.

## Decouple producers from connections

The templates separate three things:

1. The producer task, started once per stream, bounded by
   `max_duration_s`, which emits events into the hub
   ([event_hub.py.template](../assets/event_hub.py.template)).
2. The hub, which sequences events, keeps a bounded replay buffer, and fans
   events out to bounded per-subscriber queues.
3. One subscription per HTTP connection, which reads its queue and writes
   frames ([sse_endpoint.py.template](../assets/sse_endpoint.py.template)).

Because the producer never writes to a socket directly, a slow or vanished
client cannot block it, and a reconnecting client can resume from the buffer.

## Backpressure policies

| Policy | Behavior | Use when |
| --- | --- | --- |
| Disconnect slow consumer (template default) | Queue full marks the subscriber; its connection closes without `end`; client reconnects and replays | Events must not be lost and replay is available |
| Drop or coalesce | Keep only the latest progress value per key | Progress or presence updates where only the latest matters |
| Block the producer | Producer awaits queue space | Exactly one consumer and the producer can pause (rare for user-facing streams) |
| Spill to durable storage | Overflow goes to a broker or log | Consumers may be offline for long periods |

Whatever the policy, bound every buffer: replay size, per-subscriber queue
size, maximum event size, maximum streams, and maximum subscribers per stream
(`HubLimits`). Unbounded queues turn one slow client into an out-of-memory
incident.

## Detecting disconnects

- Writes fail once the peer is gone, so heartbeats bound the detection delay
  for idle streams.
- ASGI servers report disconnects either as a disconnect message or as a
  failed send. Starlette's streaming response stops the body iterator in both
  cases, which raises cancellation or an error inside the frame generator.
  The generator's `finally` block must release the subscription (the template
  cancels the pending read and closes the subscription).
- Do not cancel a pending `anext` with `asyncio.wait_for` to implement
  heartbeats: cancelling an async generator's `anext` closes the generator.
  Wait on a task with `asyncio.wait` instead, as `sse_frames` does.

## Propagating cancellation upstream

Decide per feature what a disconnect means:

| Feature | On last subscriber leaving | Template setting |
| --- | --- | --- |
| Interactive generation for one user | Cancel the producer to stop spending | `cancel_when_unobserved=True` |
| Job whose result is stored and may be reopened | Keep running; client can reconnect | `cancel_when_unobserved=False` (default) |
| Explicit stop button | Cancel through an authorized request | `DELETE /streams/{id}` calls `EventHub.cancel` |

Cancellation must reach the actual work: the producer task is cancelled,
which cancels its awaited model or tool call; the model client must pass
cancellation through to its HTTP request. Work that cannot be interrupted
safely (a payment, a write) belongs in a separate, idempotent step, not inside
the streamed producer.

When cancellation also needs to survive reconnects with a short grace period,
schedule the cancel after a delay and skip it if a subscriber returns.

## gRPC and WebSocket notes

- gRPC applies HTTP/2 flow control per stream; a server that writes faster
  than the client reads eventually awaits on send. Combine it with deadlines,
  and check the call's cancellation state in long loops.
- WebSocket libraries buffer outgoing messages; bound or monitor those
  buffers, and treat a close frame or connection loss like an SSE disconnect.

## Tests that must exist

- A slow consumer is disconnected and the producer is not blocked.
- Events published during replay are delivered exactly once.
- A disconnected subscription releases its slot.
- Cancel ends the stream with `end` status `cancelled`.
- An unobserved producer is cancelled when the policy says so.

## Sources

- [ASGI HTTP and WebSocket specification](https://asgi.readthedocs.io/en/latest/specs/www.html)
- [Starlette: StreamingResponse](https://starlette.dev/responses/#streamingresponse)
- [Python asyncio queues](https://docs.python.org/3/library/asyncio-queue.html)
- [Python asyncio.wait](https://docs.python.org/3/library/asyncio-task.html#asyncio.wait)
- [gRPC cancellation](https://grpc.io/docs/guides/cancellation/)
- [gRPC flow control](https://grpc.io/docs/guides/flow-control/)
