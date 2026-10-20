# Choosing a live-update transport

Pick the simplest transport that meets the freshness requirement. Every option
needs the same downstream discipline: validate events, apply them through the
cache owner, and resynchronize after gaps.

## Decision guide

| Requirement | Prefer | Why |
| --- | --- | --- |
| Data may be a minute old; low event rate | polling via the query layer (`refetchInterval`) | no connection state, works through every proxy |
| Server-to-client notifications only, text payloads | Server-Sent Events (`EventSource`) | built-in reconnection and `Last-Event-ID` resume, plain HTTP |
| Bidirectional, low-latency messages (presence, collaborative cursors) | WebSocket | full duplex, binary frames, subprotocols |
| Need custom request headers on the stream | `fetch` with a streamed body reader | `EventSource` and browser `WebSocket` cannot set arbitrary headers |
| Only "something changed" signals | any push channel plus query invalidation | small events, the cache refetches authoritative data |

Questions to answer before coding (record them in the
[connection contract](../assets/connection-contract.md)):

1. Does the server guarantee ordering? Per entity, per stream, or not at all?
2. Can the server replay from a cursor (`Last-Event-ID`, sequence)? For how long?
3. What does a client do after a gap: refetch everything, refetch affected keys,
   or request a replay?
4. How is the stream authenticated, and how does it end when the session expires?
5. Which close codes or HTTP statuses are terminal?
6. What heartbeat interval does the server send, and what proxy idle timeouts apply?

## Server-Sent Events specifics

- The browser reconnects automatically after network errors, waiting the
  server-provided `retry:` interval, and sends the last received `id:` as the
  `Last-Event-ID` header. Do not wrap `EventSource` in a second retry loop.
- An HTTP error status or a non `text/event-stream` content type makes the
  browser give up (`readyState === CLOSED`). Treat that as terminal and offer a
  manual retry, which creates a new `EventSource`.
- Named events (`event: order.updated`) need `addEventListener(name)`; `onmessage`
  receives only unnamed events.
- Authentication options: same-origin cookies, `withCredentials` for
  credentialed cross-origin requests (requires matching CORS), or a short-lived
  ticket in the URL. Never a long-lived bearer token in the URL.
- Over HTTP/1.1 browsers limit connections per origin (commonly six), shared
  across tabs. Prefer HTTP/2 or HTTP/3, or one shared stream per tab.

Template: [useEventSource hook](../assets/use-event-source.ts.template) with
[tests](../assets/use-event-source.test.ts.template).

## WebSocket specifics

- The browser API has no reconnection; the client owns backoff, heartbeat, and
  terminal-state detection. Template:
  [reconnecting socket](../assets/reconnecting-socket.ts.template) with
  [tests](../assets/reconnecting-socket.test.ts.template).
- Close codes: 1000 normal, 1001 going away, 1006 abnormal (never sent on the
  wire; reported locally), 1008 policy violation, 1011 server error, 4000 to 4999
  application-defined. Agree which are terminal (for example 4401 unauthorized).
- Application heartbeats (a small JSON frame every N seconds) detect half-open
  connections that TCP keepalive and browser events do not reveal promptly.
- Authenticate during the handshake with cookies or a one-time ticket fetched
  just before connecting; the `url` callback in the template exists for that.
- Use `wss:` in every non-local environment; a Content Security Policy needs a
  matching `connect-src` entry.

## Polling specifics

- `useQuery({ ...ordersQueries.list(filters), refetchInterval: 30_000 })` with
  `refetchIntervalInBackground: false` pauses while the tab is hidden.
- Add jitter on the server side or vary intervals per client when many clients
  start together (for example after a deploy).

## Sources

- HTML Living Standard, server-sent events: <https://html.spec.whatwg.org/multipage/server-sent-events.html>
- MDN, Using server-sent events: <https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events>
- MDN, WebSocket API: <https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API>
- WHATWG WebSockets standard: <https://websockets.spec.whatwg.org/>
- RFC 6455, close codes: <https://www.rfc-editor.org/rfc/rfc6455.html#section-7.4.1>
- TanStack Query, `refetchInterval`: <https://tanstack.com/query/latest/docs/framework/react/reference/useQuery>
- MDN, `connect-src`: <https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/connect-src>
