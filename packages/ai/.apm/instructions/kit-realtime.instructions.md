---
description: Apply to server-side streaming, Server-Sent Events, and WebSocket endpoints.
applyTo: "**/*stream*.py,**/*websocket*.py,**/*realtime*.py,**/*event_source*.py,**/sse/**,**/sse_*.py,**/*_sse.py"
---

- Authenticate and authorize at connection time, re-check access for each subscribed resource, and close connections when credentials expire.
- Validate the `Origin` header on WebSocket handshakes and apply the HTTP API's CORS policy to event streams.
- Validate every inbound message against a schema and enforce a maximum message size and rate per connection.
- Bound connections per user and in total, queue depth per connection, and stream duration; disconnect slow consumers instead of buffering without limit.
- Send heartbeats (SSE comment lines or WebSocket pings) at a fixed interval so proxies and clients detect dead connections.
- For Server-Sent Events, send `id:` with each event, resume from `Last-Event-ID`, and disable proxy response buffering for the route.
- Use typed, versioned event envelopes (type, id, timestamp, payload) and keep payloads small; send identifiers instead of large records.
- Never block the event loop in a connection handler; hand slow work to a task and stream its progress.
- Propagate cancellation: stop producers and release subscriptions when the client disconnects or the server shuts down.
- Use a shared broker, not process memory, when more than one server instance must fan out events.
- Close with meaningful WebSocket close codes or a final error event rather than silently dropping the stream.
- Test with a real client against a test server, covering reconnect, disconnect, slow consumers, and authorization expiry.
- Use the `kit-server-streaming` skill for endpoint design.
