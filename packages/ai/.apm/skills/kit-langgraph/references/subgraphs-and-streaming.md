# Subgraphs and streaming

## Subgraphs

A subgraph is a compiled graph used as a node of another graph. Use one when
a unit of work has its own state, routing and tests (for example a research
step used by several workflows), not merely to group code.

Two integration styles:

| Style | How | Use when |
| --- | --- | --- |
| Shared keys | Add the compiled subgraph directly as a node; overlapping state keys flow in and out | Parent and child share a clear subset of the schema |
| Wrapper node | Call the subgraph inside a node, mapping parent state to child input and child output back | Schemas differ or the child must not see parent keys |

Rules:

- Prefer the wrapper style at trust or ownership boundaries; it keeps the
  child from reading or overwriting parent keys such as status or receipts.
- Persistence: by default a subgraph uses the parent's checkpointer for the
  current invocation. Compile the child with `checkpointer=True` only when it
  must keep its own state across invocations (for example a long-lived
  sub-agent conversation), and include it in retention and access reviews.
- Interrupts inside a subgraph pause the parent. On resume, the parent node
  that called the subgraph runs again from its start; keep code before the
  subgraph call free of side effects.
- Bounds do not compose automatically: node defaults set on the parent are not
  inherited by subgraphs, so set retry policies and timeouts on the child
  explicitly, and verify how the installed version counts child steps against
  the run's recursion limit.
- Test the child graph on its own with its own fakes, then test the parent with
  the child replaced by a fake node when the child is expensive.

## Streaming

Streaming exposes progress while a run executes. Choose the mode by audience:

| Mode | Emits | Typical consumer | Exposure risk |
| --- | --- | --- | --- |
| `updates` | Node name and that node's state update | Progress indicators, logs | Updates contain state values; filter before forwarding |
| `values` | Full state after each step | Debugging | Exposes everything in state |
| `messages` | Model token chunks with metadata | Chat interfaces | Raw model output, including content later rejected |
| `custom` | Data written by nodes through the stream writer | Domain progress events | Only what you choose to emit |
| `debug` | Detailed execution events | Local diagnosis | Not for clients |

Guidance:

- Forward a projection, not raw state. `ApprovalWorkflow.stream_progress`
  yields node names only; emit domain events such as `drafting` or
  `awaiting_review` through `custom` mode when clients need more.
- Token streams show unvalidated model output. Mark streamed text as
  provisional and replace it with the validated final result, or stream only
  after validation for content that must not be shown unchecked.
- Include subgraph events only when the client needs them; they are opt-in.
- Map graph streams onto the transport in the server-streaming skill (SSE or
  WebSocket) with explicit terminal events, heartbeats and cancellation. When
  the client disconnects, cancel the graph task; the checkpoint allows a
  later resume.
- An interrupt ends the stream with an `__interrupt__` update; translate it to
  an explicit `awaiting_review` event rather than a silent close.

## Sources

- [LangGraph subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs)
- [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
