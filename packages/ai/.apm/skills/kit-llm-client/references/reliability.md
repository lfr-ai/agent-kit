# Timeouts, retries, rate limits, and circuit breaking

Model calls are slow, rate limited, and occasionally unavailable. Apply every
call policy in one wrapper around the adapter
([llm_policies.py.template](../assets/llm_policies.py.template)) so the
effective behavior is visible and testable.

## Deadlines

- Give every request a per-attempt timeout (`CompletionRequest.timeout_s`)
  and the wrapper an overall deadline covering all attempts and delays
  (`RetrySettings.total_deadline_s`).
- The wrapper shrinks each attempt's timeout to the remaining deadline, so a
  late retry cannot outlive the caller.
- Derive the overall deadline from the user operation: an interactive request
  might allow 20 to 60 seconds; a background job can allow more but must still
  be bounded.
- Streaming responses need a time-to-first-token timeout and an idle timeout
  between chunks, in addition to the total deadline.

## Retry classification

| Error | Retry? | Why |
| --- | --- | --- |
| Timeout, connection failure, 5xx, overloaded | Yes, bounded | Likely transient |
| Rate limited (429) | Yes, honor Retry-After up to a cap | Provider asked us to wait |
| Circuit open | No, fail fast | Protects the provider and our latency |
| Invalid request, unsupported parameter | No | Same request fails again |
| Context too long | No; shrink input instead | Deterministic |
| Content filtered or refused | No | Retrying is an attempt to bypass a control |
| Authentication or permission | No; alert | Configuration defect |
| Budget exceeded | No | Policy decision |
| Malformed structured output | At most one repair round | See structured output reference |

Retrying a completion re-runs generation and is billed again. Retries are safe
for the application only when the call itself has no side effects; tool calls
the model requests must be executed by your code under their own idempotency
rules.

## Backoff

Use capped exponential backoff with full jitter: the delay before retry `n` is
a uniform random value between zero and `min(max_delay, base * 2^(n-1))`.
Jitter spreads retries from many clients so they do not hit the provider in
synchronized waves. If the provider supplies Retry-After, wait at least that
long; if it asks for longer than the configured maximum, fail instead of
holding resources. Stop when the next delay would cross the overall deadline.

## Rate limits and concurrency

Providers limit requests per minute and tokens per minute, per key, model and
region. Client-side controls:

- A concurrency limit per provider and alias (`max_concurrency`) bounds
  in-flight requests and memory.
- For predictable throughput, add a token-bucket limiter keyed by tokens per
  minute, using the estimated input plus maximum output tokens per request.
- Share limits across workers through the gateway or a shared store; a
  per-process limiter alone multiplies with the number of processes.
- Reduce demand before adding capacity: smaller prompts, lower output caps,
  caching of deterministic results, and batching where the provider offers it.

## Circuit breaker

After a threshold of consecutive transient failures, the breaker opens and
calls fail immediately with `LlmCircuitOpenError` for a cool-down period, then
one probe call is allowed. This keeps a provider outage from turning into
thread or connection exhaustion, and gives callers a fast, typed signal to show
a degraded experience. Share one breaker per provider endpoint across callers.

## Cancellation

When the user cancels or disconnects, cancel the in-flight task. The wrapper
holds no state that needs cleanup beyond the concurrency slot, which is
released by the async context manager.

## Testing the policies

Inject the clock, sleep and random source. The template tests prove retry
order and delays, Retry-After handling and its cap, deadline shrinking, no
retry across the deadline, permanent errors not retried, budget refusal before
any call, breaker open and probe, the concurrency cap, and content-free logs.

## Sources

- [AWS Architecture Blog: exponential backoff and jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
- [RFC 9110: Retry-After](https://www.rfc-editor.org/rfc/rfc9110#field.retry-after)
- [OpenAI rate limits](https://platform.openai.com/docs/guides/rate-limits)
- [OpenAI error codes](https://platform.openai.com/docs/guides/error-codes)
- [Anthropic rate limits](https://docs.anthropic.com/en/api/rate-limits)
- [Azure OpenAI quotas and limits](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/quotas-limits)
- [Python asyncio synchronization primitives](https://docs.python.org/3/library/asyncio-sync.html)
