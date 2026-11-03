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
- Durable pauses, resumption and human approval mid-run are orchestration
  concerns; use existing `kit-langgraph` guidance or optional `kit-temporal`
  when the consumer already uses those runtimes. They are not interchangeable
  persistence formats.

## Framework selection

Primary framework documentation rechecked 2026-11-02. Select the existing
consumer stack first. No toolkit installs, popularity ranking or universal
framework set is implied.

| Existing option | Use for a demonstrated gap | Keep outside it |
| --- | --- | --- |
| Plain typed code | Fixed workflow, small tool set, bounded evaluator loop | No need to install an agent framework |
| LlamaIndex | Existing ingestion/index/retrieval pipeline and provenance | Resource authorization and domain records |
| DSPy | Optimizing a typed prediction program with a versioned metric/dataset | Production side effects and online train/test leakage |
| LangChain | Existing model/tool integrations or a standard agent loop | Provider policy, tool authorization and hidden retries |
| LangGraph | Explicit state, checkpoints, durable interrupts and approval | Non-idempotent effects inside replayed nodes |
| Temporal | Durable business operations across workers and long waits | Model/network calls in deterministic Workflow code |
| MCP | Tool interoperability across hosts | Control flow, authorization and durability |

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
- Start from the baseline dataset in the existing `kit-llm-evaluation` owner
  for DSPy optimization; use `kit-langgraph` when that runtime is selected. Keep
  training/validation/holdout separate and compare task success, cost and
  trajectory regressions before promotion. Do not create a duplicate
  `kit-evals` owner or add optional packages to this toolkit.
- Use framework callbacks/decorators only to connect native lifecycle hooks:
  tracing callbacks emit safe metadata, graph nodes call existing typed tools,
  DSPy modules express measured signatures. Never move access policy into a
  tracing callback or invent an abstraction solely to wrap a decorator.
- Temporal Activities may invoke the existing LLM port or an existing graph;
  document which layer owns retries and approvals. Durable replay is not
  exactly-once billing or permission to replay irreversible tool actions.

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
- [LangChain Python overview](https://docs.langchain.com/oss/python/langchain/overview)
- [DSPy optimization](https://dspy.ai/learn/optimization/overview/)
- [LlamaIndex framework](https://developers.llamaindex.ai/python/framework/)
- [Temporal durable AI](https://docs.temporal.io/ai)
- [LangChain multi-agent patterns](https://docs.langchain.com/oss/python/langchain/multi-agent)
- [CrewAI documentation](https://docs.crewai.com/) and [flows](https://docs.crewai.com/en/concepts/flows)
- [LlamaIndex agents](https://developers.llamaindex.ai/python/framework/use_cases/agents/)
- [Model Context Protocol specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
