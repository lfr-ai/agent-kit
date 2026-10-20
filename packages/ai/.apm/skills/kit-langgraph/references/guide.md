# LangGraph workflow guide

## Purpose

Design bounded, resumable graph workflows with explicit state, terminal
behavior, safe side effects, and deterministic tests. This guide maps the
references and copyable assets of the skill.

## When not to use a graph

A plain function or a short sequence of awaited calls is easier to read, test
and operate. Reach for a graph when you need at least one of: durable pauses
for human input, resumption after failure, branching with persisted state, or
streaming progress across many steps.

## References

| Topic | Reference |
| --- | --- |
| State schema design, reducers, schema evolution | [state-and-reducers.md](state-and-reducers.md) |
| Checkpointers, durability, interrupts, idempotent side effects | [persistence-and-interrupts.md](persistence-and-interrupts.md) |
| Retry policy, timeouts, recursion limit, failure statuses | [reliability.md](reliability.md) |
| Subgraph integration and stream modes | [subgraphs-and-streaming.md](subgraphs-and-streaming.md) |
| Deterministic test levels, fakes, required cases | [testing.md](testing.md) |

## Assets and copy targets

| Template | Copy to | Purpose |
| --- | --- | --- |
| [workflow_ports.py.template](../assets/workflow_ports.py.template) | `workflows/ports.py` | Ports, value objects, typed errors |
| [approval_graph.py.template](../assets/approval_graph.py.template) | `workflows/approval_graph.py` | Graph, nodes, facade (`ApprovalWorkflow`) |
| [test_approval_graph.py.template](../assets/test_approval_graph.py.template) | `tests/workflows/test_approval_graph.py` | Deterministic path, retry, interrupt and checkpoint tests |
| [graph_template.json.template](../assets/graph_template.json.template) | design review | Declarative summary of nodes, edges, interrupts, retries and limits |

The templates were written against `langgraph` 1.x. Read the installed
version's documentation before relying on any API, especially retry, timeout
and streaming options, which have changed between releases.

## Acceptance gates

- State schema is typed, minimal, versioned, and free of secrets.
- Every node has a path to `END`; conditional edges declare their destinations.
- Retries apply only to transient errors, with bounded attempts and jitter.
- Model and tool calls have per-attempt timeouts; runs have a recursion limit.
- Side effects run in their own node with a stable idempotency key.
- Interrupt resume values are validated and the resumer is authorized.
- Checkpoints have an access, encryption and retention decision.
- Tests cover each terminal path, retries, interrupts, recovery from a
  checkpoint, and an incompatible checkpoint version.

## Failure modes

- Missing terminal path leading to runs that stop only at the recursion limit.
- Checkpoint schema drift that prevents or corrupts resume across versions.
- Side effects placed before an `interrupt()` and repeated on resume.
- Unbounded tool or model calls inside a node without a timeout or budget.
- Raw state or unvalidated tokens streamed to clients.

## Negative cases

- Force a node to fail permanently and verify the failed status and no retry.
- Exhaust retries, then verify a later call resumes from the checkpoint.
- Seed a checkpoint with an older schema version and verify rejection.
- Resume with a malformed decision and verify the thread stays paused.

## Scope and limits

The assets are a reference implementation with tests against the in-memory
checkpointer. They do not certify a production checkpointer, a hosting
platform, or model quality; add an integration test with the real saver.

## Sources

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
