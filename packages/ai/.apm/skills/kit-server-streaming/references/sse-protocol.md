# Server-Sent Events protocol and stream contract

## Wire format

An SSE response has `Content-Type: text/event-stream` and a UTF-8 body of
events separated by blank lines. Each line is a field:

| Field | Meaning | Contract in the templates |
| --- | --- | --- |
| `id` | Sets the client's last event id | Per-stream sequence number starting at 1 |
| `event` | Event type; default `message` | `start`, `delta`, `progress`, `end` |
| `data` | Payload line; multiple lines join with newlines | One line of compact JSON |
| `retry` | Reconnection delay in milliseconds | Sent once at connection start |
| `: text` | Comment, ignored by clients | Heartbeat `: ping` |

[stream_events.py.template](../assets/stream_events.py.template) encodes
frames, parses them like a browser does, and rejects payloads that could
break framing: data is single-line JSON, names come from an enum, and ids are
integers, so no field can inject a blank line or a forged event.

## Stream contract

Write the contract down and test it from the client side
([test_sse_endpoint.py.template](../assets/test_sse_endpoint.py.template)):

- Events carry contiguous sequence ids starting at 1.
- `start` is first; `delta` and `progress` carry documented payloads; clients
  ignore unknown event names so the server can add types compatibly.
- Exactly one `end` event closes a completed stream, with `status` of
  `completed`, `failed`, `cancelled` or `timeout`, and a safe error category
  when failed. A partial result is never presented as complete unless `end`
  says `completed`.
- A connection that closes without `end` is a transport interruption. The
  client reconnects with `Last-Event-ID` and receives only later events.
- The validator [verify_stream_events.py](../assets/verify_stream_events.py)
  checks recorded manifests such as
  [stream_template.json.template](../assets/stream_template.json.template)
  against these rules.

## Reconnection and resume

Browsers reconnect automatically after a network error, waiting the `retry`
delay, and send the last seen id in the `Last-Event-ID` request header. The
server must:

1. Parse the header strictly; reject malformed values with 400.
2. Replay events after that id from a bounded buffer, then continue live,
   without a gap or duplicate between replay and live delivery (the hub takes
   the replay snapshot and registers the subscriber without an intervening
   await).
3. Answer 409 (or another non-200 status the client treats as fatal) when the
   needed events were evicted, so the client restarts deliberately.
4. Answer 204 No Content when the stream already ended and nothing is left to
   replay; a browser `EventSource` stops reconnecting on 204.

Replay requires the buffer to outlive short disconnects. Size it from the
event rate times the longest reconnect you support, and expire closed streams
after a retention period (`EventHub.forget`).

## Heartbeats

Proxies and load balancers close idle connections. Send a comment frame when
no event has been sent for an interval shorter than the smallest idle timeout
on the path (the template uses 15 seconds). Heartbeats also surface dead
connections sooner, because writes to a closed socket fail.

## Authentication

- Authenticate and authorize before sending the first byte; once the status
  line is sent, errors can only be expressed as events.
- The browser `EventSource` API cannot set custom headers. Use same-site
  cookies, or a fetch-based SSE client that sends an `Authorization` header.
  Never put tokens in the query string; URLs end up in logs and histories.
- Re-check authorization on every reconnect, and bound connection lifetime so
  revoked access takes effect.

## SSE over POST

Some protocols stream SSE in response to POST (the request body carries the
input). This works with fetch-based clients but not with `EventSource`, and
automatic reconnection is then the client's job.

## Browser connection limits

Over HTTP/1.1, browsers allow only a few concurrent connections per origin,
shared across tabs; several open SSE streams can starve other requests. Serve
SSE over HTTP/2 or multiplex several logical streams over one connection.

## Sources

- [HTML Living Standard: server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [MDN: EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- [MDN: Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [FastAPI: Server-Sent Events](https://fastapi.tiangolo.com/tutorial/server-sent-events/)
- [Starlette: StreamingResponse](https://starlette.dev/responses/#streamingresponse)
