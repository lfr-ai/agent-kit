# Proxies, load balancers, and timeouts

Most streaming defects in production come from infrastructure between the
server and the client: buffering, idle timeouts, compression, and connection
draining. Verify the deployed path end to end in a safe environment; local
tests cannot prove it.

## Buffering

A buffering proxy collects the response before forwarding it, so the client
sees nothing until the stream ends.

- Send `Cache-Control: no-cache` (the template adds `no-transform`) so caches
  and transforming proxies leave the stream alone.
- For nginx, disable proxy buffering for the route, or send
  `X-Accel-Buffering: no` from the application (the template does).
- Exclude `text/event-stream` from response compression middleware; gzip
  buffers output to compress it efficiently.
- CDNs and API gateways may buffer by default; check whether they support
  streaming responses for your route and plan.

## Idle and maximum timeouts

| Layer | Typical setting to check | Mitigation |
| --- | --- | --- |
| Reverse proxy | Read timeout between bytes from upstream | Heartbeat interval below it |
| Cloud load balancer | Idle connection timeout (often around 60 seconds by default) | Heartbeats; raise the timeout for the route if needed |
| CDN or edge proxy | Origin response and idle timeouts | Heartbeats; verify the limit for streamed responses |
| Application server | Keep-alive and graceful shutdown timeouts | Bounded connection lifetime; drain on deploy |
| Client | Fetch or EventSource behavior on errors | Reconnect with `Last-Event-ID` |

Set the heartbeat (`StreamSettings.heartbeat_s`) comfortably below the
smallest idle timeout on the path, and set the connection lifetime
(`max_connection_s`) below any hard maximum so the server, not the
infrastructure, closes the connection at a clean point.

## Deployments and scaling

- Long-lived connections pin clients to old instances. Bound connection
  lifetime so clients reconnect and land on new instances, and give the
  server a graceful shutdown window that closes streams cleanly.
- With several replicas, a reconnect may reach a different instance. Either
  route by stream id (sticky routing) or back the hub interface with a shared
  log so any instance can replay and continue the stream.
- Count open streams per instance and include them in autoscaling signals;
  CPU alone underestimates load for mostly idle connections.

## HTTP versions

- HTTP/1.1: one stream per TCP connection; browsers cap connections per
  origin. Prefer HTTP/2 to the client for multiple streams.
- HTTP/2: many streams share a connection; intermediaries must support it end
  to end or downgrade transparently.
- WebSockets need upgrade support on every hop and usually separate idle
  timeout settings.

## Verification checklist

1. Through the real path, the first event arrives before the producer
   finishes (no buffering).
2. A stream idle longer than the load balancer timeout stays open thanks to
   heartbeats.
3. A deploy or instance restart produces reconnects that resume without gaps.
4. Closing the client cancels or detaches upstream work as the contract says.
5. Error responses (401, 403, 404, 409) reach the client as statuses, not as
   broken streams.

## Sources

- [nginx: proxy_buffering](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_buffering)
- [nginx: X-Accel-Buffering](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_ignore_headers)
- [AWS Application Load Balancer connection idle timeout](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/application-load-balancers.html#connection-idle-timeout)
- [Uvicorn settings: timeouts](https://uvicorn.dev/settings/#timeouts)
- [HTML Living Standard: server-sent events authoring notes](https://html.spec.whatwg.org/multipage/server-sent-events.html#authoring-notes)
- [RFC 9111: HTTP caching, no-transform](https://www.rfc-editor.org/rfc/rfc9111#name-no-transform)
