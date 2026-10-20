# Server streaming guide

## Purpose

Author server-to-client streaming endpoints with a written contract, bounded
resources, resumable delivery, propagated cancellation, and explicit
partial-result semantics. This guide maps the references and copyable assets.

## References

| Topic | Reference |
| --- | --- |
| SSE versus WebSocket versus gRPC versus chunked HTTP | [transport-selection.md](transport-selection.md) |
| Framing, stream contract, `Last-Event-ID`, heartbeats, authentication | [sse-protocol.md](sse-protocol.md) |
| Bounded queues, slow consumers, disconnects, upstream cancellation | [backpressure-and-cancellation.md](backpressure-and-cancellation.md) |
| Buffering, idle timeouts, deployments, verification checklist | [proxies-and-timeouts.md](proxies-and-timeouts.md) |

## Assets and copy targets

| Asset | Copy to | Purpose |
| --- | --- | --- |
| [stream_events.py.template](../assets/stream_events.py.template) | `streaming/events.py` | Event contract, SSE codec, replay buffer, SSE parser |
| [event_hub.py.template](../assets/event_hub.py.template) | `streaming/hub.py` | Producers, fan-out, replay, backpressure, cancellation |
| [sse_endpoint.py.template](../assets/sse_endpoint.py.template) | `streaming/sse.py` | FastAPI routes with heartbeats and connection lifetime |
| [test_stream_events.py.template](../assets/test_stream_events.py.template) | `tests/streaming/` | Codec, parser, replay buffer |
| [test_event_hub.py.template](../assets/test_event_hub.py.template) | `tests/streaming/` | Ordering, replay race, slow consumer, producer outcomes |
| [test_sse_endpoint.py.template](../assets/test_sse_endpoint.py.template) | `tests/streaming/` | Client contract: statuses, headers, framing, resume |
| [stream_template.json.template](../assets/stream_template.json.template) | fixture | Recorded stream in the contract format |
| [verify_stream_events.py](../assets/verify_stream_events.py) | run in place or in CI | Validates recorded event manifests |

Run the validator on recordings:

```text
python verify_stream_events.py recording.json [--allow-open] [--max-event-bytes N] [--allow-event NAME]
```

It prints `path:line: message` per finding and exits 1 on findings, 2 on
unreadable input.

## Acceptance gates

- Event names, payload fields, sequence ids and the single terminal `end`
  event with its status values are documented and tested from the client side.
- Authentication and authorization complete before the first byte; no
  credentials in query strings.
- Heartbeat interval is below the smallest idle timeout on the deployed path,
  and buffering is disabled end to end.
- Reconnect with `Last-Event-ID` resumes without gaps or duplicates; evicted
  replay and finished streams have explicit statuses.
- Queues, replay buffers, event size, stream count and connection lifetime
  are bounded.
- Disconnect and explicit cancel reach the producer as the contract specifies.

## Failure modes

- Streams that never terminate because no terminal event or lifetime exists.
- Partial streams interpreted as successful completions by the client.
- Proxy buffering or compression delaying all output until completion.
- Slow consumers growing server memory without bound.
- Heartbeats implemented with a cancelling wait that closes the subscription.

## Negative cases

Slow consumer, disconnect mid-stream, reconnect after eviction, reconnect to a
finished stream, unauthorized reader, malformed `Last-Event-ID`, producer
timeout, producer failure, explicit cancel, empty completion.

## Scope and limits

The assets and validator check application behavior and recorded payloads.
They do not validate a specific proxy, load balancer or CDN; use the
verification checklist in the proxies reference against the deployed path.

## Sources

- [HTML Living Standard: server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [gRPC core concepts](https://grpc.io/docs/what-is-grpc/core-concepts/)
