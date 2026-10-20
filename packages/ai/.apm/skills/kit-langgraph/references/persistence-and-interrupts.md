# Persistence, checkpointing, and human-in-the-loop interrupts

## Checkpointers

Compiling a graph with a checkpointer saves a snapshot of state after each
super-step, keyed by `thread_id` in `config["configurable"]`. Persistence is
what makes interrupts, failure recovery, and inspection possible.

| Saver | Use | Notes |
| --- | --- | --- |
| `InMemorySaver` | Unit tests, notebooks | Lost on restart; never in production |
| SQLite saver | Single-process tools, local development | One writer; file permissions matter |
| PostgreSQL saver | Production services | Call `setup()` once via migrations; keep `thread_id` under the column limit |
| Managed platform persistence | When the platform runs the graph | Read its retention and access model |

Operational rules:

- Treat checkpoints as sensitive persisted data: define who can read them,
  encrypt at rest (the checkpoint library offers an encrypting serializer
  keyed from the environment), and set a retention period with deletion.
- Derive `thread_id` from a stable business identifier (the template uses
  `approval:<request_id>`); this makes `start` idempotent and lets operators
  find a thread. Do not put personal data in the id.
- Choose a durability mode deliberately: `sync` writes each checkpoint before
  the next step (safest), `async` overlaps writes with execution, `exit` writes
  only when the run ends or pauses (fastest, loses intermediate progress on a
  crash).
- Checkpoints are not an audit log. Write audit events (who approved what,
  when) to an append-only store owned by the application.

## Interrupts

Calling `interrupt(payload)` inside a node saves state and pauses the run. The
invoke result contains `__interrupt__` with the payload. Resuming with
`Command(resume=value)` and the same `thread_id` re-enters the node, and
`interrupt()` returns `value`.

Rules that prevent the common defects:

1. The node restarts from its beginning on resume. Everything before
   `interrupt()` runs again, so it must be free of side effects (the
   template's `review` node only reads state before pausing).
2. The resume value is untrusted input. Validate it after `interrupt()` returns
   (`parse_decision`) and also before resuming at the API boundary, so a
   malformed decision returns a typed error and leaves the thread paused.
3. Interrupt payloads must be JSON-serializable and should contain only what
   the reviewer needs; they are persisted and returned to clients.
4. Authorize the resumer. Whoever can call `resume` decides the outcome; check
   that the caller may review this thread before resuming.
5. Check that the thread is actually waiting (`snapshot.next` contains the
   interrupting node) and that its schema version matches before resuming.
6. Multiple simultaneous interrupts (parallel branches) are resumed with a
   mapping from interrupt id to value; keep one interrupt per decision point
   unless parallel review is a requirement.
7. Define what happens when nobody answers: a reminder, an expiry job that
   resumes with an explicit `expire` decision, or thread deletion after the
   retention period. A paused thread waits indefinitely.

## Static breakpoints versus dynamic interrupts

Static breakpoints (`interrupt_before` or `interrupt_after` at compile or run
time) pause around whole nodes and suit debugging. Dynamic `interrupt()` calls
suit product workflows because the payload and condition are explicit in code.

## Side effects around pauses and retries

A node may execute more than once: after a retryable failure, after a crash
before its checkpoint was written, and (for code before `interrupt()`) on
resume. Therefore:

- Give every external side effect an idempotency key derived from stable state
  (`<request_id>:apply`), and make the gateway return the original receipt for
  a repeated key.
- Put side effects in their own node after the decision node, never in the
  same node before an interrupt.
- Record the receipt in state so operators can see the side effect happened.

## Time travel and manual repair

Saved checkpoints can be listed (state history) and a thread can be updated or
forked from an earlier checkpoint. Treat these as operator tools behind
authorization and audit, not as application features, and never use them to
bypass a pending human decision.

## Sources

- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- [LangGraph time travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
