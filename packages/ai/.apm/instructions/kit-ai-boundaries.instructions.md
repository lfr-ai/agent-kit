---
description: Apply to model orchestration, retrieval, queues, and AI-adjacent infrastructure.
applyTo: "**/*prompt*,**/prompts/**,**/*agent*,**/agents/**,**/*llm*,**/*queue*,**/queues/**"
---

- Keep model/provider calls behind explicit adapters; core policy must not depend on SDKs.
- Bound tokens, concurrency, retries, queue depth, stream duration, and total resource use; set an explicit timeout on every provider call.
- Validate model output and tool arguments against a schema at every trust boundary; treat a parse failure as an error, not a reason for unlimited retries.
- Give agents only the tools their task needs, and require approval for tools with external side effects.
- Keep agent and graph state typed and serializable; checkpoint only data you are allowed to retain.
- Make every agent or graph loop terminate: cap steps and recursion and define an explicit failure exit.
- Make queued tasks idempotent, pass identifiers instead of large or sensitive payloads, and set retry limits with backoff and a dead-letter path.
- Preserve retrieval provenance and enforce access rules before content reaches a model.
- Treat prompts, model responses, checkpoints, and queue payloads as potentially sensitive data.
- Do not log credentials, personal content, prompts, or full provider responses by default; record identifiers, versions, token counts, and latency instead.
- Keep production authorization and data policy authoritative outside the model.
- Never acquire Azure credentials or assume a cloud identity is available.
- Use synthetic fixtures and fake model responses for tests; report provider, cloud, and production checks as unverified unless run.
- Use the `kit-langgraph`, `kit-llm-client`, or `kit-task-queue` skill for the matching procedure.
