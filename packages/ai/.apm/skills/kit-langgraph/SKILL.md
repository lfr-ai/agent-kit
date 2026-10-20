---
name: kit-langgraph
description: Use when designing or reviewing bounded LangGraph workflows with explicit state, control flow, and recovery.
license: MIT
---

# Make graph execution bounded and inspectable

## Procedure

1. Read the installed LangGraph version and existing graph conventions before
   using an API; confirm retry, timeout, interrupt and streaming signatures.
2. Decide whether a graph is needed at all; a plain function is preferable
   unless you need durable pauses, resumption, persisted branching or
   streamed progress ([references/guide.md](references/guide.md)).
3. Define ports for every model, tool and side-effecting system, with typed
   transient and permanent errors
   ([workflow_ports.py.template](assets/workflow_ports.py.template)).
4. Define the state schema as the minimal, typed, versioned information nodes
   and the resume path need; add reducers only for keys several nodes update
   ([state-and-reducers.md](references/state-and-reducers.md)).
5. Keep nodes focused on one transformation or boundary call; route on
   explicit status values and declare every conditional destination,
   including terminal paths.
6. Bound execution: per-attempt timeouts, retry policies for transient errors
   only, a recursion limit, and token or cost budgets in the model port
   ([reliability.md](references/reliability.md)).
7. Put side effects in their own node with a stable idempotency key; never
   before an `interrupt()` in the same node.
8. Choose a durable checkpointer, durability mode, encryption, access, and
   retention; derive `thread_id` from a stable business id
   ([persistence-and-interrupts.md](references/persistence-and-interrupts.md)).
9. Make interrupt and resume boundaries explicit: validate and authorize the
   resume value, check the thread is waiting, and check its schema version.
10. Treat model output and tool results as untrusted; validate before they
    update state or trigger work.
11. Hide graph types behind a small facade that returns caller-facing statuses
    ([approval_graph.py.template](assets/approval_graph.py.template)).
12. Stream a safe projection of progress, not raw state, and handle
    subgraph persistence and bounds explicitly
    ([subgraphs-and-streaming.md](references/subgraphs-and-streaming.md)).
13. Test routing, retries, timeouts, interrupts, recovery and checkpoint
    compatibility with fakes and the in-memory saver
    ([testing.md](references/testing.md),
    [test_approval_graph.py.template](assets/test_approval_graph.py.template)).
14. Record the reviewed shape in
    [graph_template.json.template](assets/graph_template.json.template) when a
    design review needs a declarative summary.

## Acceptance gates

- Typed, versioned state schema without secrets; resume refuses or migrates
  other versions.
- Every node reaches `END`; a test asserts the terminal edges.
- Retries only for transient errors with bounded attempts; permanent errors
  end the run with a typed status.
- Per-call timeouts, a recursion limit, and budgets are configured and tested.
- Side effects are idempotent by key and proven to run once.
- Interrupt resume is validated, authorized, and tested for malformed input.
- Checkpointer choice, durability mode, encryption, and retention are recorded.
- Streams expose only an intended projection.

## Failure modes

- Unbounded recursion or missing terminal nodes.
- Checkpoint incompatibility across deployments.
- Side effects repeated by retries or by resuming an interrupted node.
- Prompts, private state or tokens logged or streamed by default.
- A graph introduced where a simple function expresses the policy more clearly.
