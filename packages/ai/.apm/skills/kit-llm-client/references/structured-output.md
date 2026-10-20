# Structured output validation

Prompt wording, JSON modes and schema-constrained decoding all reduce
malformed output; none of them proves that the output is correct for your
domain. Validate every structured result in code.

## Layers of defense

1. Ask for a schema. Pass a JSON Schema derived from the validation model
   (`json_schema` on the request). Providers that support strict schema
   decoding follow it closely; others treat it as a hint.
2. Parse defensively. Strip a single surrounding code fence, then parse. Do not
   search arbitrary text for the first brace; that accepts partial output.
3. Validate with a typed model. Pydantic validates types, required fields,
   ranges and custom rules (for example "due date after issue date").
4. Check the finish reason. `length` means truncated output: raise, and fix the
   output cap or the prompt. `content_filter` means a refusal: surface it as a
   typed error, never retry around it.
5. Repair at most once. Send the validation problems back (location and error
   type only, never the offending values) and accept the second answer only if
   it validates. More rounds cost money and rarely help.
6. Fail typed. After the repair budget, raise `StructuredOutputError`; callers
   decide whether to show a fallback, queue for review, or abort.

[structured_output.py.template](../assets/structured_output.py.template)
implements these steps; the tests cover valid output, fences, one repair,
repeated failure, truncation and filtering.

## Schema design

- Keep schemas small and flat; deeply nested optional structures increase
  invalid output.
- Use enums for categorical fields and explicit nullability instead of
  optional fields with ambiguous meaning.
- Forbid additional properties so silently invented fields are rejected.
- Express numeric units in field names (`total_cents`) and validate ranges.
- Version the schema with the prompt; a schema change is a prompt change.

## Business validation

Schema validity is not truth. After validation:

- Cross-check extracted values against source data the application already
  holds (for example totals equal the sum of line items).
- Treat identifiers produced by the model as untrusted lookups: verify they
  exist and that the caller may access them.
- Never execute model-produced code, queries or URLs without an allow-list and
  the caller's permissions.

## Tool and function calling

Tool calls are structured output that triggers actions:

- Validate arguments with the same rigour as any API input.
- Authorize each tool call as the end user, not as the service.
- Make side-effecting tools idempotent and require confirmation for
  irreversible actions.
- Bound the number of tool-call rounds per request.

## Sources

- [OpenAI structured outputs](https://platform.openai.com/docs/guides/structured-outputs)
- [LiteLLM JSON mode and response_format](https://docs.litellm.ai/docs/completion/json_mode)
- [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/)
- [Pydantic validation errors](https://docs.pydantic.dev/latest/errors/validation_errors/)
- [JSON Schema specification](https://json-schema.org/specification)
- [OWASP Top 10 for LLM applications: improper output handling](https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/)
