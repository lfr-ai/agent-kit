# Tools, guardrails, budgets and evaluation

Reviewed 2026-10-23.

## Tool design

| Property | Rule |
| --- | --- |
| Narrow | One job per tool; prefer `get_order_status` to a generic `query_database` |
| Typed | Declared parameters with exact types, lengths and units; unknown arguments fail |
| Documented | Description says when to use it, what it returns and which error codes exist |
| Idempotent | Side-effecting tools accept an idempotency key derived from run id and step |
| Bounded | Timeout, result size limit and pagination; never return unbounded data |
| Safe errors | Stable error codes the model can act on; no stack traces or provider messages |
| Least privilege | Credentials scoped to the tool, never visible to the model |

The [tool contract](../assets/agent_tool_contract.py.template) implements an
allow-listed registry with argument validation, deny-by-default approval for
side effects, deduplication by idempotency key and stable error codes.
Evaluate tool descriptions like prompts: a renamed parameter or reworded
description changes selection accuracy.

## Context and memory

- Build each step's context explicitly: instructions, goal, tool
  definitions, and a bounded window of recent observations. Summarize or drop
  older observations by a written rule, not by provider truncation.
- Keep large artifacts out of context; pass identifiers and fetch slices
  through tools.
- Long-term memory is a data store with an owner, schema, retention, access
  control and deletion path. Never write user content to shared memory
  without consent and tenant isolation.
- Retrieved text, tool results and other agents' outputs are untrusted data;
  instructions inside them are not followed.

## Guardrails

| Layer | Check | On failure |
| --- | --- | --- |
| Input | Scope, prompt-injection patterns, size, tenant | Refuse or route to a human |
| Tool call | Allow-list, schema, authorization of the end user, approval for side effects | Return a stable error code |
| Output | Schema, policy, citations or evidence, no secrets | Repair once, then fail with a typed error |
| Run | Step, cost, time and repetition budgets | Stop with an explicit outcome |

- Authorization is enforced by code on behalf of the end user, never by
  instructions to the model.
- Human approval applies to irreversible or external effects: payments,
  emails, deletions, deployments, access changes. Show the exact arguments.
- Guardrails run in code before and after the model; a guardrail model is
  one more classifier with its own evaluation.

## Budgets and loop limits

Every run has, and tests prove:

- a maximum number of steps,
- a maximum cost, checked after each model call and before the next,
- a wall-clock deadline for the whole run plus per-call timeouts,
- a limit on identical repeated actions (loop detection), and
- a maximum delegation depth (one by default).

The [supervisor loop](../assets/supervisor_loop.py.template) returns an
explicit outcome for each limit; callers handle every outcome. Do not raise a
budget to make an evaluation pass; investigate why the run needs more steps.

## Observability

- One trace per run, one span per step, with run id, step index, action
  kind, target, argument digest, cost, latency and outcome. Follow the
  OpenTelemetry generative AI agent span conventions for attribute names, or
  Langfuse traces with observations per step.
- Capture prompt and tool content only when approved; the template records
  argument digests, not values.
- Correlate gateway spans and tool spans with the run trace.

## Evaluating trajectories

| Metric | Measures |
| --- | --- |
| Task success | Final outcome meets the goal's expected result |
| Tool selection accuracy | Expected tools called, unexpected ones not called |
| Argument accuracy | Arguments match expected values for key steps |
| Efficiency | Steps, cost and latency per successful run |
| Redundancy | Repeated or unnecessary calls |
| Policy violations | Unapproved side effects, denied tools requested, budget stops |

- Build a goal dataset with expected outcomes and, for critical paths, an
  expected tool sequence or set; score with the `kit-llm-evaluation` harness
  and its gates.
- Compare against a non-agent baseline (single call or workflow); keep the
  agent only if it wins on the gating metrics at acceptable cost.
- Run each goal several times; agent trajectories vary more than single calls.

## Primary sources

- [Anthropic: Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [OpenAI Agents SDK guardrails](https://openai.github.io/openai-agents-python/guardrails/)
- [OpenAI Agents SDK tracing](https://openai.github.io/openai-agents-python/tracing/)
- [MCP tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [OpenTelemetry generative AI agent spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/)
- [Langfuse observability](https://langfuse.com/docs/observability/overview)
- [OWASP Top 10 for LLM applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
