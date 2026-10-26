---
description: Apply to agent loops and tool implementations exposed to language models.
applyTo: "**/agents/**/*.py,**/tools/**/*.py"
---

- Treat every model-proposed tool call as untrusted input: check the allow-list, validate arguments against a typed schema, and reject unknown arguments.
- Each tool has one narrow job, a documented description and error codes, a timeout, and a bounded result size.
- Return stable error codes to the model; never pass stack traces, provider messages or credentials into model context.
- Side-effecting tools take an idempotency key and require approval for irreversible or external effects; authorization is checked in code for the end user.
- Every agent run has step, cost, wall-clock and repeated-action limits, and each limit ends the run with an explicit outcome.
- Workers do not delegate further unless a design review approves deeper delegation.
- Trace steps with ids, action kinds, targets and argument digests; capture prompt or tool content only when approved.
- Use the `kit-agent-systems` skill for pattern choice, tool contracts, budgets and trajectory evaluation.
