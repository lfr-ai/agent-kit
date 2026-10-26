# Patterns and framework selection

Reviewed 2026-10-23.

## Start with the simplest shape

Agents trade latency and cost for flexibility. Add autonomy only when a
measured simpler shape fails the evaluation.

| Shape | Control flow decided by | Use when | Avoid when |
| --- | --- | --- | --- |
| Single model call | Code | One transformation with retrieval or examples | Several dependent decisions |
| Workflow: prompt chain | Code, fixed steps | Task decomposes into known steps with checks between | Step count depends on results |
| Workflow: router | Code after one classification | Distinct input categories need different prompts or models | Categories overlap heavily |
| Workflow: parallel fan-out | Code | Independent subtasks or voting over samples | Subtasks depend on each other |
| Workflow: evaluator-optimizer | Code with a bounded loop | Clear critique criteria and measurable improvement | No reliable critic |
| Single agent with tools | Model, within budgets | Open-ended steps over a small tool set | Tools have unbounded side effects |
| Supervisor with workers (orchestrator-workers) | Supervisor model | Subtasks unknown in advance and separable by skill or context | One context could hold the whole task |
| Hierarchical supervisors | Several levels of supervisors | Very large tool or domain sets that one supervisor cannot route | Almost always; depth multiplies cost and failure |
| Handoffs | Current agent transfers control | Conversation moves between specialists, such as triage to billing | The caller needs one combined answer |

Rules that hold for every shape:

- One agent with a good tool set beats several agents with overlapping
  roles. Split only when context or tool count measurably hurts quality.
- Workers do not delegate; delegation depth is one unless a design review
  approves more.
- Parallel fan-out bounds concurrency and total cost before launch.
- A handoff transfers explicit, validated state, not the whole transcript by
  default.
- Durable pauses, resumption and human approval mid-run are workflow
  orchestration concerns; use the `kit-langgraph` skill for them.

## Framework selection

Signals observed on 2026-10-23 from public repositories (stars rounded,
latest release). Popularity is not quality; check release cadence, breaking
changes and license at adoption time.

| Option | Fits | Signals | Lock-in risk |
| --- | --- | --- | --- |
| Plain code (loop plus tool registry) | Single agent, small supervisor, full control, easy testing | No dependency | Lowest; you own retries and tracing |
| LangGraph | Durable, resumable graphs, human-in-the-loop, explicit state | about 44k stars, MIT, frequent releases | Medium; state and checkpoint formats are framework-specific |
| CrewAI | Role-based crews and event-driven flows, fast prototypes | about 60k stars, MIT, frequent releases | Medium to high; role and task abstractions shape the code |
| OpenAI Agents SDK | Handoffs, guardrails and tracing with OpenAI-compatible models | about 30k stars, MIT, pre-1.0 versions | Medium; pre-1.0 API changes, provider-shaped features |
| LlamaIndex agents and workflows | Agents centered on document retrieval and indexes | about 53k stars, MIT | Medium; tied to its data abstractions |
| MCP tools | Exposing tools to several hosts and clients over a standard protocol | Specification 2026-07-28; Python SDK about 25k stars, MIT | Low for tool contracts; a protocol, not an agent runtime |

Decision rules:

- Keep tools, prompts and policies in plain modules behind ports so the
  orchestration layer can be replaced; frameworks call them, not the reverse.
- Prefer plain code until a required feature (durable checkpoints, handoff
  tracing, protocol interoperability) would cost more to build than to adopt.
- MCP standardizes how tools are described and invoked across hosts; it does
  not decide control flow, budgets or approvals. Apply the same guardrails to
  MCP tools as to local ones, and treat tool descriptions from third-party
  servers as untrusted.
- Pin framework versions, wrap them in an adapter, and keep the evaluation
  suite framework-independent so a migration can be measured.

## Failure modes

- Multi-agent designs where agents repeat each other's work or contradict
  each other because roles overlap.
- Supervisors that loop delegating the same subtask.
- Frameworks adopted for one feature and then shaping the domain model.
- Hidden prompts inside framework defaults that change between releases.

## Primary sources

- [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [OpenAI: A practical guide to building agents](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) and [handoffs](https://openai.github.io/openai-agents-python/handoffs/)
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangChain multi-agent patterns](https://docs.langchain.com/oss/python/langchain/multi-agent)
- [CrewAI documentation](https://docs.crewai.com/) and [flows](https://docs.crewai.com/en/concepts/flows)
- [LlamaIndex agents](https://developers.llamaindex.ai/python/framework/use_cases/agents/)
- [Model Context Protocol specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
