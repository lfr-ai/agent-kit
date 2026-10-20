# Choosing a streaming transport

Pick the simplest transport that satisfies the direction of data, the client
platforms, and the infrastructure between them. Most "stream a result to a
browser" features need Server-Sent Events, not WebSockets.

## Decision table

| Need | Prefer | Why |
| --- | --- | --- |
| Server pushes progress or tokens to a browser; client sends commands with normal requests | SSE | Plain HTTP, automatic reconnect with `Last-Event-ID`, works through most proxies |
| Low-latency bidirectional messages (collaboration, games, interactive terminals) | WebSocket | Full duplex on one connection |
| Service-to-service streaming with typed contracts | gRPC server or bidirectional streaming | Protobuf schemas, deadlines, cancellation and HTTP/2 flow control built in |
| Download of a large generated file or newline-delimited records | Chunked HTTP response (for example NDJSON) | No event semantics needed; any HTTP client can consume |
| Infrequent updates, restrictive networks, or very old clients | Long polling | Works everywhere; higher latency and request overhead |
| Fan-out to many consumers across services | A broker plus one of the above at the edge | Decouples producers from connection handling |

## Comparison

| Property | SSE | WebSocket | gRPC streaming |
| --- | --- | --- | --- |
| Direction | Server to client | Both | Server, client, or both |
| Framing | Text events (`id`, `event`, `data`, `retry`) | Text or binary messages | Length-prefixed protobuf messages |
| Reconnect and resume | Built into browsers; resume via `Last-Event-ID` | Application must implement | Application must implement |
| Authentication in browsers | Cookies, or a fetch-based client for headers | Cookies or a token in the first message; no custom headers in browser API | Metadata headers; not native in browsers |
| Backpressure | TCP only; server must bound buffers | TCP only; library-level buffers | HTTP/2 flow control per stream |
| Cancellation signal | Client closes the connection | Close frame or connection loss | Explicit cancellation propagated with deadlines |
| Proxy friendliness | High, if buffering is disabled | Needs upgrade support and idle timeouts | Needs end-to-end HTTP/2 |
| Contract documentation | Event catalog (for example AsyncAPI) | AsyncAPI or custom | `.proto` files |

## Questions to settle before building

1. Who sends what? If the client only sends occasional commands, use normal
   requests for commands and SSE for updates.
2. What happens on disconnect: resume from the last event, restart the work,
   or show a partial result as failed? Write it down as the stream contract.
3. Which proxies, load balancers, CDNs and gateways sit in the path, and what
   are their idle timeouts and buffering defaults? See
   [proxies-and-timeouts.md](proxies-and-timeouts.md).
4. How many concurrent connections per user and per instance must be
   supported, and what memory does each cost?
5. Does a long-lived connection need re-authorization when permissions change
   or a session expires? Bound connection lifetime so it is re-checked.

## Sources

- [HTML Living Standard: server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [MDN: Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [RFC 6455: The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
- [gRPC core concepts](https://grpc.io/docs/what-is-grpc/core-concepts/)
- [gRPC flow control](https://grpc.io/docs/guides/flow-control/)
- [AsyncAPI specification](https://www.asyncapi.com/docs/reference/specification/latest)
