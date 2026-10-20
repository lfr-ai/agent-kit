# Server streaming guide

Purpose

Detailed references, copyable templates, and tests are indexed in [references/guide.md](references/guide.md).

Checklist for authoring server-to-client streaming endpoints with clear lifecycle, cancellation, and partial-result semantics.

Acceptance gates

- Event framing and terminal markers are defined and documented.
- Cancellation and client disconnect are propagated to upstream work.
- Buffering behavior and proxies are understood for the deployment target.

Failure modes

- Streams that never terminate due to missing terminal event.
- Partial streams interpreted as successful completions by the client.
- Buffering at proxies causing large memory growth or timeouts.

Verification prerequisites

- End-to-end mock client and server tests verifying disconnects and resume behavior.
- Tests for slow consumers and mid-event disconnect.

Authoritative references

- Server-Sent Events (EventSource): <https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events>
- gRPC streaming concepts: <https://grpc.io/docs/what-is-grpc/core-concepts/>

Scope and limits

This guide is an authoring checklist. It does not validate specific infra proxy behavior (which varies by deployment). Use end-to-end tests for any infra-sensitive assumptions.
