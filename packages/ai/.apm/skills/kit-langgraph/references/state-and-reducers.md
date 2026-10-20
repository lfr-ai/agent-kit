# State schemas and reducers

State is the contract between nodes and the persisted record of a thread.
Every key is checkpointed, may be shown to reviewers, and must survive a
deployment that changes the code reading it.

## Designing the schema

- Store what later nodes and the resume path need; nothing else. Large
  payloads (documents, files) belong in a store addressed by id.
- Use a `TypedDict` (or dataclass or Pydantic model) with concrete types.
  The template builds a fully populated initial state so every node can read
  every key without `KeyError` guards.
- Prefer flat, JSON-friendly values. The default serializer handles common
  types; custom classes and pickle fallback make checkpoints fragile across
  deployments.
- Keep secrets, access tokens and raw credentials out of state. Persisted
  state outlives the request and is visible to anyone who can read the
  checkpointer.
- Record provenance needed for audit (model id, prompt version, reviewer id)
  as explicit keys rather than in free-form history strings.
- Add a `schema_version` key and refuse or migrate threads written by another
  version before resuming them (`IncompatibleCheckpointError` in the template).

## Reducers

A node returns a partial update. For each key, the graph either overwrites the
value (the default) or merges it with a reducer declared through `Annotated`:

```python
class State(TypedDict):
    status: str  # last write wins
    history: Annotated[list[str], operator.add]  # appended across nodes
```

| Pattern | Reducer | Use for | Risk |
| --- | --- | --- | --- |
| Last write wins | none | Status, scalars, single owner keys | Parallel branches writing the same key raise an error |
| Append | `operator.add` | Audit trail, collected results | Unbounded growth; cap or summarize |
| Merge by id | custom function | Collections updated by several nodes | Must be pure, deterministic, and order-independent where branches run in parallel |
| Message list | the message reducer from the framework | Chat transcripts | Transcript size and personal data in checkpoints |

Reducer rules:

- Reducers must be pure functions of `(current, update)`; they run during
  replay and must give the same result every time.
- Parallel branches (fan-out with edges or `Send`) that update the same key in
  one super-step need a reducer; otherwise the update is ambiguous.
- Bound growth. An append-only list in a long-running thread becomes the
  dominant checkpoint cost; trim it in a node or keep a counter instead.

## Inputs, outputs, and private state

Graphs can declare separate input and output schemas so callers cannot set
internal keys and do not receive them. Use this for any key that must not be
caller-controlled (for example `status` or `receipt_id`). The template achieves
the same through `ApprovalWorkflow`, which builds the initial state itself and
returns a small `WorkflowStatus` instead of raw state.

## Routing on state

- Conditional edges should read explicit status values, not infer state from
  the presence of optional keys.
- Declare the possible destinations of each conditional edge so the compiled
  graph shows every path, including terminal ones; the template test asserts
  the edges to `__end__` exist.
- Every non-terminal node needs a path to `END`. A graph that can only stop
  through the recursion limit is defective.

## Schema evolution checklist

1. Adding a key: give it a default in the initial state and tolerate its
   absence when resuming older threads, or bump the version.
2. Removing or renaming a key: bump `STATE_SCHEMA_VERSION`; drain or migrate
   paused threads first.
3. Changing a reducer or routing meaning: treat as a version bump; replays of
   old checkpoints would otherwise compute different results.
4. Test resume of a checkpoint written by the previous version before release.

## Sources

- [LangGraph Graph API: state and reducers](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph Graph API how-to](https://docs.langchain.com/oss/python/langgraph/use-graph-api)
- [Python typing.TypedDict](https://docs.python.org/3/library/typing.html#typing.TypedDict)
- [Python typing.Annotated](https://docs.python.org/3/library/typing.html#typing.Annotated)
