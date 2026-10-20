# Provider abstraction

Model providers, SDKs and prices change faster than the features built on
them. Put one narrow port between the application and every provider, and
keep provider choice a configuration decision.

## The port

[llm_port.py.template](../assets/llm_port.py.template) defines:

- `CompletionRequest`: operation name, model alias, messages, output token
  cap, temperature, per-attempt timeout, optional JSON schema, prompt name
  and version, and a correlation id. Invalid requests fail at construction.
- `Completion`: text, served model, finish reason, token usage, cost when
  known, latency, attempts, and safe metadata.
- A typed error hierarchy split into transient errors (timeout, unavailable,
  rate limited, circuit open) and permanent errors (invalid request, context
  too long, content filtered, authentication, budget, structured output).
- `LlmClient`: one async `complete` method that adapters, policy wrappers and
  fakes all implement.

Application code imports only the port. It never imports a provider SDK, never
sees provider exception types, and never chooses a concrete model string.

## Model aliases

Use aliases named for the job (`summarizer`, `classifier`, `extractor`). The
adapter maps aliases to concrete provider models from configuration. Benefits:

- Swapping a model or provider is a configuration change reviewed with an
  evaluation run, not a code search.
- Budgets, price tables and metrics key on stable names.
- A deprecated model is replaced in one place.

## Gateway options

| Option | What it gives | Costs |
| --- | --- | --- |
| Direct vendor SDK in an adapter | Full feature access, fewest moving parts | One adapter per provider |
| Multi-provider library in-process (for example LiteLLM's SDK) | One call shape and one exception family across providers | Large dependency; feature lag for new provider options |
| Self-hosted gateway or proxy (for example LiteLLM's proxy) | Central keys, quotas, caching, logging and routing | Another service to secure, operate and keep patched |
| Managed cloud gateway | Quotas, content safety, private networking | Vendor coupling; regional availability |

Whichever you choose, it sits behind the same port.
[litellm_adapter.py.template](../assets/litellm_adapter.py.template) shows the
in-process option: it resolves aliases, sets `num_retries=0` so retries stay
in one visible policy layer, passes a JSON schema when requested, and maps the
library's exceptions to the port's errors. It maps by exception type, never by
parsing messages, and never copies provider messages into its errors because
they can echo prompt content.

## Credentials and configuration

- Load API keys from the environment or a secret store at the adapter or
  gateway; never place them in request objects, prompts, logs, or aliases.
- Prefer workload identity or short-lived tokens where the provider supports
  them; scope keys per environment and per service.
- Pin the gateway or SDK version and read its changelog for changes to
  defaults (retries, timeouts, parameter dropping).

## Fallbacks and routing

Fallback to another model or provider is a product decision: outputs differ in
quality, safety behavior, data residency and price.

- Route only between aliases that passed the same evaluation suite.
- Never fall back across a data-residency or contractual boundary implicitly.
- Record the served model on every completion (`Completion.model`) so quality
  incidents can be traced.
- Fall back on transient errors only; a content-filter refusal from one
  provider is not a reason to try another.

## Data minimization

Send only what the task needs. Strip identifiers that do not change the
answer, keep untrusted input in the user message with clear delimiters, and
confirm the provider's retention and training terms for the data class you
send.

## Sources

- [LiteLLM exception mapping](https://docs.litellm.ai/docs/exception_mapping)
- [LiteLLM reliable completions and retries](https://docs.litellm.ai/docs/completion/reliable_completions)
- [LiteLLM proxy overview](https://docs.litellm.ai/docs/simple_proxy)
- [OpenAI API reference](https://platform.openai.com/docs/api-reference)
- [Anthropic API errors](https://docs.anthropic.com/en/api/errors)
- [OWASP Top 10 for LLM applications: sensitive information disclosure](https://genai.owasp.org/llmrisk/llm022025-sensitive-information-disclosure/)
