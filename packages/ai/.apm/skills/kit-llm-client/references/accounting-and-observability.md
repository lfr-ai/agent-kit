# Accounting, logging, redaction, and prompt versioning

## Token and cost accounting

- Record input and output tokens from the provider's usage report for every
  successful call (`Completion.usage`). Do not estimate when the provider
  reports actual usage.
- Record cost when the provider or gateway reports it; otherwise compute it
  from a versioned price table keyed by model alias (`Price` in the policies
  template). Leave cost unknown rather than guessing for unpriced models.
- Enforce caps before dispatch: a per-request token cap (estimated input plus
  the requested output cap) and a spend cap per scope such as tenant per day
  or batch job (`SpendBudget`). The character-based estimate is pessimistic;
  use the model tokenizer when a cap must be exact.
- Aggregate tokens and cost by operation, alias, served model, prompt version
  and tenant. These dimensions explain most cost regressions.
- Retries are billed. Report attempts per call next to cost.

## What to log

One structured record per attempt, with metadata only:

| Field | Purpose |
| --- | --- |
| `operation`, `model_alias`, `model` | Which feature and which model served it |
| `prompt_name`, `prompt_version` | Trace quality changes to prompt changes |
| `request_id` | Correlate with the user request and traces |
| `attempt`, `outcome` | Retry behavior and error categories |
| `finish_reason` | Truncation and refusals |
| `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms` | Capacity and spend |

Do not log by default: prompts, completions, tool arguments, retrieved
documents, provider error messages, or request headers. They contain user data
and sometimes credentials.

## Redaction

[redaction.py.template](../assets/redaction.py.template) provides a safety net
for the places text can still leak:

- `redact` replaces bearer tokens, API-key-like strings, credential
  assignments, email addresses, long digit sequences and JWT-like tokens.
- `safe_preview` produces a short, redacted preview for opt-in debug logging.
- `RedactingFilter` redacts every record passing through a handler; attach it
  to handlers that receive third-party SDK logs.

Pattern-based redaction misses things. Treat it as a second line of defense
behind "do not log content", never as permission to log content.

When content capture is required (debugging an incident, building an
evaluation set), make it opt-in per environment, store it separately with
access control and a short retention period, and record who enabled it.

## Tracing

Emit a span per model call with the same metadata as the log record. The
OpenTelemetry generative AI semantic conventions define attribute names for
operation, model, token usage and finish reasons; their content-capture
options should stay disabled by default.

## Prompt versioning

- By default keep prompts in code as `PromptTemplate` values with a name and an
  explicit version; bump the version for any wording change. For independently
  approved managed versions, use [prompt-management.md](prompt-management.md).
- The template fingerprint (a hash of the text) catches edits made without a
  version bump; assert it in a test that pins the expected fingerprint.
- Placeholders are explicit; rendering fails on missing or extra variables.
- Untrusted text goes only into the user message, inside clear delimiters,
  with system instructions telling the model to treat it as data.
- Every completion carries the prompt name and version in logs and traces, and
  evaluation results are stored per prompt version.

## Sources

- [LiteLLM token usage and cost](https://docs.litellm.ai/docs/completion/token_usage)
- [OpenTelemetry semantic conventions for generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [Python logging filters](https://docs.python.org/3/library/logging.html#filter-objects)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Top 10 for LLM applications: prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
