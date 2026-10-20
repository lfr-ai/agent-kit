---
description: Apply to browser clients for WebSocket, Server-Sent Events, and streamed responses.
applyTo: "**/*socket*.ts,**/*socket*.tsx,**/*stream*.ts,**/*stream*.tsx,**/*realtime*.ts,**/*realtime*.tsx,**/*event-source*.ts"
---

- Own each connection in one module or hook that exposes typed events and connection state; components must not open sockets directly.
- Validate every incoming message at the boundary and report unknown event types instead of crashing.
- Reconnect with capped exponential backoff and jitter; stop after authorization failures and surface that state to the user.
- Resume from the last processed event id when the server supports it, and deduplicate events by id.
- Close connections, abort streamed fetches with `AbortController`, and clear timers when the owner unmounts or inputs change.
- Show connecting, live, reconnecting, and offline states accessibly; announce important updates through a polite live region instead of moving focus.
- Merge pushed updates into the existing server-state cache instead of keeping a parallel copy.
- Throttle or batch high-frequency updates before rendering.
- Never put long-lived credentials in URLs or query strings; use the short-lived token or cookie flow the server contract defines.
- Test with a fake server or mocked transport covering disconnect, reconnect, duplicate, and out-of-order events.
- Use the `kit-client-realtime` skill for the client procedure.
