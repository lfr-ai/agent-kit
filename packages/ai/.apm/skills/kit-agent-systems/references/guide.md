# Agent systems guide

## Purpose

Design single-agent and multi-agent systems that are no more autonomous than
the task needs, with typed tools, explicit budgets, guardrails, traces and
trajectory evaluation. Durable graph execution belongs to `kit-langgraph`;
model calls to `kit-llm-client`; evaluation mechanics to `kit-llm-evaluation`.

## References

| Topic | Reference |
| --- | --- |
| Workflow versus agent, supervisor, hierarchical, handoffs, router, fan-out, framework selection | [patterns-and-frameworks.md](patterns-and-frameworks.md) |
| Tool design, context and memory, guardrails, budgets, observability, trajectory evaluation | [tools-guardrails-and-evaluation.md](tools-guardrails-and-evaluation.md) |

## Assets and copy targets

| Asset | Copy to | Depends on |
| --- | --- | --- |
| [agent_design.md.template](../assets/agent_design.md.template) | design review record | none |
| [agent_tool_contract.py.template](../assets/agent_tool_contract.py.template) | `agents/tools.py` | stdlib |
| [supervisor_loop.py.template](../assets/supervisor_loop.py.template) | `agents/supervisor.py` | stdlib |

Connect the two modules with a small gateway adapter: call
`ToolRegistry.call` with the step key and return an `Observation` whose
content is the bounded result or the error code. Replace `ScriptedModel` with
an adapter over the `kit-llm-client` port that parses the model's tool call
into `CallTool`, `Delegate` or `Finish` and rejects anything else.

## Verification

- Unit tests with the scripted model: completion, each budget outcome,
  repeated-action detection, unknown worker, and a trajectory without
  argument values.
- Tool registry tests: unknown tool, invalid and extra arguments, `bool`
  rejected for `int`, approval denied, replay with the same idempotency key
  executing once, and stable error codes without exception text.
- Trajectory evaluation on a goal dataset against a non-agent baseline.

## Limits

The templates run offline with fakes. They do not call a model, enforce
end-user authorization (the consumer's tools must), persist state across
process restarts, or provide a sandbox for tools.
