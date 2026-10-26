---
name: kit-agent-systems
description: Use when designing or reviewing agentic or multi-agent systems, their tools, guardrails, and budgets.
license: MIT
---

# Design agents that stay bounded and measurable

## Procedure

1. Write the goal, success criteria and a goal dataset first; fill the
   [design worksheet](assets/agent_design.md.template).
2. Choose the simplest shape that can pass: single call, workflow (chain,
   router, fan-out, evaluator loop), single agent with tools, then
   supervisor with workers or handoffs
   ([patterns-and-frameworks.md](references/patterns-and-frameworks.md)).
3. Keep delegation depth at one; workers never delegate. Use `kit-langgraph`
   when runs need durable pauses, resumption or mid-run approval.
4. Design narrow, typed, documented tools with stable error codes, timeouts,
   bounded results and idempotency keys for side effects
   ([agent_tool_contract.py.template](assets/agent_tool_contract.py.template)).
5. Allow-list tools per agent; enforce end-user authorization in tool code
   and require human approval for irreversible or external effects.
6. Build context explicitly per step, keep large data behind tools, treat
   retrieved text and tool output as untrusted, and give memory an owner,
   retention and deletion path
   ([tools-guardrails-and-evaluation.md](references/tools-guardrails-and-evaluation.md)).
7. Enforce step, cost, wall-clock and repetition limits with an explicit
   outcome for each ([supervisor_loop.py.template](assets/supervisor_loop.py.template)).
8. Route every model call through the `kit-llm-client` port and validate
   each proposed action before executing it.
9. Trace one span per step with run id, action kind, target, argument digest,
   cost and outcome; capture content only when approved.
10. Evaluate task success and trajectories with `kit-llm-evaluation` against
    a non-agent baseline, with repeated runs.
11. Select a framework only when a needed feature outweighs its lock-in;
    keep tools and policies framework-independent. The asset map and adapter
    notes are in [references/guide.md](references/guide.md).

## Acceptance gates

- The design record states why a simpler shape was rejected, with evidence.
- Every tool has a typed schema, documented error codes, a timeout and a
  side-effect class; unknown tools and extra arguments are rejected.
- Side-effecting calls require approval and run once per idempotency key.
- Tests prove each budget outcome, loop detection and unknown-target handling.
- Traces contain no prompt or tool content unless approved.
- Trajectory metrics and task success meet declared gates and beat or match
  the non-agent baseline at acceptable cost.

## Failure modes

- Autonomy added where a workflow was enough, multiplying cost and variance.
- Overlapping roles and unbounded delegation loops.
- Tool injection: instructions in retrieved or tool text being followed.
- Side effects repeated after a retry or replay.
