# LLM client integration guide

## Purpose

Integrate language-model providers behind an application boundary with
explicit budgets, deadlines, typed errors, validated outputs, and privacy
controls. This guide maps the references and copyable assets of the skill.

## References

| Topic | Reference |
| --- | --- |
| Port design, model aliases, gateways, credentials, fallbacks | [provider-abstraction.md](provider-abstraction.md) |
| Deadlines, retry classification, backoff, rate limits, circuit breaker | [reliability.md](reliability.md) |
| Schemas, parsing, repair, business validation, tool calls | [structured-output.md](structured-output.md) |
| Tokens, cost, budgets, logging, redaction, tracing, prompt versions | [accounting-and-observability.md](accounting-and-observability.md) |
| Evaluation sets, graders, reporting, gates | [evaluation.md](evaluation.md) |

## Assets and copy targets

| Template | Copy to | Depends on |
| --- | --- | --- |
| [llm_port.py.template](../assets/llm_port.py.template) | `llm/port.py` | stdlib |
| [llm_policies.py.template](../assets/llm_policies.py.template) | `llm/policies.py` | port |
| [structured_output.py.template](../assets/structured_output.py.template) | `llm/structured.py` | port, pydantic 2 |
| [redaction.py.template](../assets/redaction.py.template) | `llm/redaction.py` | stdlib |
| [fake_llm.py.template](../assets/fake_llm.py.template) | `llm/fakes.py` | port |
| [litellm_adapter.py.template](../assets/litellm_adapter.py.template) | `llm/adapters/litellm.py` | litellm |
| [llm_request_template.json.template](../assets/llm_request_template.json.template) | design review or fixture | none |

Tests: [policies](../assets/test_llm_policies.py.template),
[structured output](../assets/test_structured_output.py.template),
[LiteLLM adapter](../assets/test_litellm_adapter.py.template),
[prompts and redaction](../assets/test_prompt_and_redaction.py.template).
None of them sends a model request.

## Acceptance gates

- Application code depends only on the port; provider SDKs live in adapters.
- Every request has an output cap, a per-attempt timeout, and an overall deadline.
- Only transient errors are retried, with capped jittered backoff that honors
  Retry-After up to a limit; permanent errors are never retried.
- Token and spend caps are enforced before dispatch.
- Structured outputs are schema-validated, truncation and refusals are typed
  errors, and repair is bounded.
- Logs and traces carry metadata only; redaction guards remaining leak paths.
- Prompts are versioned and every completion is attributable to a prompt
  version and served model.

## Failure modes

- Silent retries that duplicate side effects or multiply cost.
- Prompts, completions or provider messages in logs or telemetry.
- Missing timeouts causing latency spikes and resource exhaustion.
- Schema-valid output accepted as true without business validation.
- Implicit fallback to a model or region with different data terms.

## Negative cases

Malformed JSON, truncated output, refusal, rate limiting with and without
Retry-After, provider outage, authentication failure, context too long,
budget exhaustion, circuit open, and cancellation.

## Scope and limits

The assets cover the client boundary and are tested with fakes and LiteLLM's
mock responses. They do not certify a model, a provider's quotas, or output
quality; consult the concrete provider documentation and run evaluations.

## Sources

- [OpenAI API reference](https://platform.openai.com/docs/api-reference)
- [LiteLLM documentation](https://docs.litellm.ai/docs/)
