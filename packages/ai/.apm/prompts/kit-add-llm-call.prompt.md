---
description: Add a language-model call behind a narrow adapter with deadlines, bounded retries, token and cost budgets, validated output, and private logging.
argument-hint: What the call does, e.g. "summarize an uploaded document"
agent: agent
---

# Add a language-model call

Integrate one model call so the application sees a typed request and result,
bounded cost and latency, and explicit failure modes.

## Input

- The user-supplied argument describes the task the model performs. Ask for
  the latency budget and data sensitivity if they are not documented.

## Procedure

1. Load [kit-llm-client](../skills/kit-llm-client/SKILL.md) and follow its
   procedure. If the call is one step in a multi-step workflow with pauses or
   resumption, also load [kit-langgraph](../skills/kit-langgraph/SKILL.md).
2. Check whether the project already has a model adapter. Extend it rather
   than adding a second SDK integration.
3. Read the installed SDK version's documentation for async use, error types,
   structured output, and retry behavior; do not rely on memory.
4. Define an application-level port: a typed request (task inputs only) and a
   typed result or a typed failure. Keep SDK types inside the adapter.
5. Send only the data the task needs. Delimit untrusted input from
   instructions and keep prompts versioned in code.
6. Set connect, response, and total deadlines that fit the user operation.
7. Retry only transient transport errors and rate limits, with bounded
   attempts and backoff that respects provider guidance; never retry invalid
   requests or exhausted quota.
8. Bound input and output tokens, concurrency, and per-operation spend before
   dispatch.
9. Validate structured output at runtime and return a typed failure for
   malformed content or refusals. Do not claim schema or determinism
   guarantees from prompt wording alone.
10. Keep prompts and responses out of normal logs; record model, latency, token
    counts, and failure category only.
11. Write tests with a fake adapter and synthetic responses: success, timeout,
    rate limit, refusal, malformed output, and outage.

## Acceptance gates

- [ ] The application core imports no provider SDK.
- [ ] Deadlines, retry limits, and token budgets are configured and tested.
- [ ] Every failure maps to a typed result the caller handles.
- [ ] No prompt or response content appears in logs.

## Output

The port definition summary, budgets chosen with reasons, files changed, test
results, and behavior that only a real provider call can confirm.
