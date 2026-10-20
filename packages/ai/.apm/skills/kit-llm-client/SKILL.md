---
name: kit-llm-client
description: Use when integrating a language-model provider behind a bounded, validated, privacy-aware application boundary.
license: MIT
---

# Make model calls predictable

## Procedure

1. Keep provider SDKs and gateways inside adapters and expose the narrow
   request, result and error contract in
   [llm_port.py.template](assets/llm_port.py.template); read
   [provider-abstraction.md](references/provider-abstraction.md).
2. Read the installed SDK or gateway documentation for the exact version,
   async behavior, default retries, and exception types; disable hidden
   retries in the adapter
   ([litellm_adapter.py.template](assets/litellm_adapter.py.template)).
3. Address models by job-named aliases resolved from configuration; load
   credentials from the environment or a secret store only.
4. Set an output cap and per-attempt timeout on every request and an overall
   deadline per user operation.
5. Classify errors as transient or permanent; retry only transient ones with
   capped, jittered backoff that honors Retry-After up to a limit
   ([reliability.md](references/reliability.md),
   [llm_policies.py.template](assets/llm_policies.py.template)).
6. Bound concurrency per provider, add a circuit breaker, and share rate
   limits across processes through the gateway or a shared store.
7. Enforce token and spend budgets before dispatch and account actual usage
   and cost after each call.
8. Validate structured output with a typed model, treat truncation and
   refusals as typed errors, and allow at most one repair round
   ([structured-output.md](references/structured-output.md),
   [structured_output.py.template](assets/structured_output.py.template)).
9. Version prompts, keep untrusted text in the user message, and record prompt
   name, version and served model on every call.
10. Log and trace metadata only; keep prompts, completions and provider
    messages out of normal logs and attach redaction to remaining paths
    ([accounting-and-observability.md](references/accounting-and-observability.md),
    [redaction.py.template](assets/redaction.py.template)).
11. Send only data required for the task and apply the application's
    retention, residency and privacy policy to every provider.
12. Test timeout, refusal, malformed output, rate limiting, outage, budget and
    breaker behavior with the scripted fake
    ([fake_llm.py.template](assets/fake_llm.py.template)) and the copied tests
    listed in [references/guide.md](references/guide.md).
13. Measure output quality with an evaluation set before changing a prompt,
    model or parameter ([evaluation.md](references/evaluation.md)).
14. Do not claim deterministic output or schema guarantees based only on
    prompt wording or temperature.

## Acceptance gates

- No provider import outside adapters; callers see only port types and errors.
- Every request has an output cap, per-attempt timeout, and overall deadline.
- Retries are limited to transient errors, bounded, jittered, and tested.
- Budgets refuse oversized requests before any call; usage and cost are
  recorded per operation, alias and prompt version.
- Structured outputs are validated; malformed, truncated and filtered outputs
  return typed errors.
- Logs contain no prompt or completion content; a test proves it.
- A request manifest such as
  [llm_request_template.json.template](assets/llm_request_template.json.template)
  documents the operation, alias, prompt version, caps and schema.

## Failure modes

- Duplicate side effects or cost from silent SDK-level retries.
- Sensitive content in logs, traces, or provider error messages.
- Unbounded tokens, concurrency, or latency.
- Implicit fallback across providers with different data terms.
