# Testing graphs deterministically

Graph tests must not call a real model, a real external system, or a real
clock. Inject ports, use the in-memory checkpointer, script every outcome,
and assert on persisted state and returned statuses.

## Test pyramid for a graph

| Level | What | Tool |
| --- | --- | --- |
| Pure functions | Validators, routers, reducers, decision parsing | Plain unit tests, parametrized negative cases |
| Single node | Boundary nodes with fake ports, timeouts, error translation | Call the node method directly with a state dict |
| Graph shape | Nodes, edges, terminal reachability | `compiled.get_graph()` nodes and edges |
| Paths | Every route to `END`, interrupts and resumes | `InMemorySaver`, scripted fakes, facade calls |
| Persistence compatibility | Resume of checkpoints from the previous schema version | Seed state with `update_state`, then resume |
| Model behavior | Prompt and output quality | Separate evaluation suite, not unit tests |

[test_approval_graph.py.template](../assets/test_approval_graph.py.template)
implements the first five levels for the approval workflow.

## Fakes

- Scripted model: returns a queue of drafts or raises queued errors; counts
  calls so retries are observable.
- Recording gateway: idempotent by key and records what was applied; lets a
  test prove the side effect happened exactly once.
- Stalling dependency: waits on an event that never fires; combined with a tiny
  timeout it proves timeouts convert to `TransientError` without sleeping.

Keep fakes behaviorally faithful to the port contract (idempotency, error
types); a fake that is more forgiving than production hides defects.

## Determinism

- Retry settings in tests: zero initial interval, jitter off. Production
  settings keep both.
- Thread ids are unique per test; the in-memory saver is created per test.
- Never assert on timestamps or generated ids from the framework; assert on
  your own state keys and statuses.
- Run async graphs with `asyncio.run` or the project's async test plugin; do
  not mix event loops across tests.

## Cases every graph needs

1. Happy path to each terminal outcome.
2. Each conditional edge's alternative branch.
3. Transient failure retried and recovered; retries exhausted; permanent
   failure not retried.
4. Interrupt payload content; resume with each allowed decision; malformed
   decision rejected while the thread stays paused.
5. Resume of an unknown thread and of a thread that is not paused.
6. Starting the same business id twice does not repeat work.
7. Recovery: after exhausted retries, a later call resumes from the
   checkpoint instead of starting over.
8. Incompatible checkpoint version refused (or migrated).
9. Side effects applied exactly once per idempotency key.
10. Stream output contains only the intended projection.

## Testing with a real checkpointer

Add an integration test that runs the happy path against the production
checkpointer (for example PostgreSQL in a container), including a process
restart between pause and resume. This proves serialization of every state
key and the durability mode in use.

## Sources

- [LangGraph testing](https://docs.langchain.com/oss/python/langgraph/test)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [pytest parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html)
