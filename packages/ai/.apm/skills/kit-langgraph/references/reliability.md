# Retries, timeouts, and execution bounds

A graph is a loop that can call models and tools. Without explicit bounds it
can spend unbounded time and money, or repeat side effects. Bound every
dimension and test each bound.

## Bounds to set

| Bound | Mechanism | Template default |
| --- | --- | --- |
| Steps per run | `recursion_limit` in the run config | 12 |
| Attempts per node | `RetryPolicy(max_attempts=...)` on `add_node` | 3 |
| Retry delay | `initial_interval`, `backoff_factor`, `max_interval`, `jitter` | 0.5 s doubling to 10 s, jittered |
| One model or tool call | `asyncio.timeout` inside the node (or the node timeout option where the installed version supports it) | 30 s |
| Whole request | Deadline at the caller, propagated as cancellation | Set by the API layer |
| Tokens and cost | Budget enforced by the model client port | See the LLM client skill |
| Loop iterations inside agents | Remaining-steps check or an explicit counter in state | Route to a terminal node before the limit |

## Retry policy

- Retry only failures that are safe and likely to succeed on retry: timeouts,
  connection errors, rate limiting, temporary unavailability. The template
  retries only `TransientError`; ports translate provider exceptions into
  `TransientError` or `PermanentError` so the graph never inspects SDK types.
- Never retry validation failures, refusals, authorization errors, or unusable
  model output; raise `PermanentError` and end the run with a typed status.
- Retries re-run the whole node. Keep nodes small so a retry repeats one
  boundary call, and make side effects idempotent.
- Use jitter in production to avoid synchronized retry storms; disable it and
  set a zero interval in tests to keep them deterministic and fast.
- Count attempts in metrics; a rising retry rate is an early outage signal.

## Recursion limit

The recursion limit caps super-steps per invocation and raises
`GraphRecursionError` when exceeded. Treat that error as a defect signal, not
a normal outcome:

- Set the limit just above the longest legitimate path (the approval graph has
  five steps; twelve leaves room for a bounded revision loop).
- For agent loops, route to a terminal "give up" node proactively using a
  remaining-steps value or a counter, so the user receives a clear outcome.
- Catch `GraphRecursionError` at the facade, log it with the thread id, and
  return a failed status.

## Timeouts and cancellation

- Wrap each external call in `asyncio.timeout` and convert the timeout to
  `TransientError` so the retry policy decides what happens next.
- The per-attempt timeout times the maximum attempts plus delays must fit
  inside the caller's deadline; otherwise the caller gives up while the graph
  keeps spending.
- Propagate cancellation: when the HTTP request is cancelled, cancel the graph
  task. The last checkpoint lets a later call resume.

## Failure outcomes

The facade maps every failure to a status the caller can act on:

| Failure | Status | Retryable | Caller action |
| --- | --- | --- | --- |
| Invalid input | `invalid` | no | Fix the request |
| `PermanentError` | `failed` | no | Show the error category; no automatic retry |
| Retries exhausted | `failed` | yes | Call `start` again later; it resumes from the checkpoint |
| Step limit | `failed` | no | Investigate; this indicates a routing defect |
| Paused | `awaiting_review` | not applicable | Present the draft to an authorized reviewer |

## Sources

- [LangGraph Graph API how-to: retry policies and timeouts](https://docs.langchain.com/oss/python/langgraph/use-graph-api)
- [LangGraph Graph API: recursion limit](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- [Python asyncio.timeout](https://docs.python.org/3/library/asyncio-task.html#asyncio.timeout)
- [AWS Architecture Blog: exponential backoff and jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
