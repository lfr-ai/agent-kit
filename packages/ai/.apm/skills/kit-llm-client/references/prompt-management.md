# Managed prompts with Langfuse

## Select the boundary

Keep code-owned `PromptTemplate` values when review and release already satisfy
the use case. Select managed prompts only when independently controlled wording
and rollout are needed. Langfuse is optional; these assets install no dependency,
credentials, telemetry exporter, model provider, or deployment automation.
Provider and prompt-service SDK imports stay in adapters.

| Selector | Use | Contract |
| --- | --- | --- |
| Explicit version | Reproducible evaluation, controlled releases | Numeric identifier of the saved version; not a model-output determinism guarantee |
| Explicit label | Independently approved environment rollout | Mutable pointer; record the actual returned version on every operation |

Require exactly one selector. Do not rely on the SDK's implicit `production`
selection or use `latest` for a release. A missing label fails rather than
silently selecting another label. Labels do not prove evaluation or approval.
Version identifiers belong to their named prompt and project, not a global
ordering or compatibility scheme.

## Copy and connect

1. Copy [the selection contract](../assets/managed_prompts.py.template),
   [the adapter contract](../assets/langfuse_prompts.py.template), and
   [the offline tests](../assets/test_managed_prompts.py.template) to their
   documented targets beside [the existing port](../assets/llm_port.py.template).
2. Supply a consumer-owned `PromptSdk` facade around the consumer's pinned
   Langfuse SDK. Its `get_prompt` forwards the name and explicit `version` or
   `label`, `type="chat"`, and `cache_ttl_seconds`. Pass the required cache TTL
   from consumer settings when constructing `LangfusePromptSource`; it must be a
   nonnegative actual integer, not a boolean. Return `SdkChatPrompt` by projecting
   the result's `name`, `version`, and raw `prompt` fields. The adapter requires a
   positive actual integer version before accepting it; strings, floats and
   booleans are rejected rather than coerced. Do not pass an SDK fallback.
   Supply the concrete fetch exception types documented
   by that installed SDK; test missing-label, authentication, transport and
   timeout failures. Never classify every `Exception` as an outage.
3. Store exactly a static system message followed by a user message with the
   existing port's `$document`-style variables. This intentionally narrow
   adapter uses `PromptTemplate.render`, not Langfuse `compile`: native
   `{{variable}}` syntax, unresolved prompt-reference tags, tools, additional
   message fields and message placeholders are rejected. Do not select composed
   prompts: the SDK may resolve references before projection, so this shape
   check cannot prove that a stored prompt has no dependencies. Escape literal
   dollar signs in the user template with `$$`. Review any migration between
   renderers explicitly; do not silently convert syntax.
4. Call `prepare_prompt` once per operation, before dispatching a model request.
   Copy its messages, name and numeric version to `CompletionRequest`.
   Rendering requires exactly the expected variables; missing or extra keys
   fail without echoing their names or values. Untrusted values only enter
   the user message.
5. Feed the request through the existing
   [reliability and budget policies](reliability.md). The prompt adapter adds
   no retry loop or second cache. SDK prompt fetching is synchronous; keep it
   off an async event loop and budget fetch time separately within the
   operation's overall deadline. Configure the installed SDK's timeout/retry
   controls in the consumer facade; model-call deadlines do not cover it.

The facade is a projection contract, not a claim that every SDK release directly
implements these Python types. The copied tests use a scripted fake, not an
installed SDK, SDK cache, Langfuse service, or a model session.

## Cache, failures and fallback

Langfuse SDKs cache prompts locally. A fresh cache hit avoids fetching; an expired
entry can be served while background revalidation updates it. A cache miss must
fetch. Cache TTL policy belongs in consumer settings; this adapter requires it
explicitly instead of duplicating an SDK default. TTL zero disables caching,
increasing latency and outage exposure. Cache lifetime is not a guaranteed
maximum stale interval if refresh keeps failing.

Moving a label does not synchronously invalidate every process's SDK cache.
Choose an acceptable convergence window, monitor the resolved version across
instances, and test an explicit refresh or version-pin redeployment for urgent
rollback. Do not report cache-hit, cache-age or refresh-success metadata unless
the installed SDK actually exposes those facts.

The shipped policy is **fail closed, no fallback**. On cold start with an empty
cache, a fetch failure raises `ManagedPromptUnavailable`; no completion request
is returned and no model should be called. Unsupported prompt shapes, identity
mismatches and invalid variables raise `ManagedPromptError`, not a fetch outage.
There is no substitution of `latest`, another prompt, or an old local version.

If a consumer explicitly approves offline fallback, review a local versioned
`PromptTemplate` with the same output and privacy contract and a separate
evaluation run. Select it only for the approved fetch-failure category, never
for invalid variables, invalid credentials, or unsupported content. Emit an
allowlisted fallback event and reason code, attribute the request to the local
fallback's own version, and count/alert on fallback use. Do not claim it is the
requested remote version or silently clear the failure. This extension does
not implement that optional policy.

## Promote, monitor and roll back

1. Save a new version without moving the production label. Record the candidate
   and previously approved version, schema/config compatibility, release owner
   and rollback decision.
2. Evaluate both exact versions on the same fixed, approved dataset snapshot;
   keep held-out cases, deterministic checks and calibrated human/judge scoring.
   Record prompt version, model configuration, evaluator/rubric version, dataset
   identity, quality thresholds, cost, latency and failure-rate results. Follow
   [evaluation.md](evaluation.md); do not evaluate through a mutable label.
3. Have the authorized operator move the rollout label to the approved candidate.
   Record the old and new targets and approval evidence. Re-read label state
   before mutation to avoid overwriting a concurrent promotion.
4. Observe actual resolved versions and quality/error signals, accounting for
   SDK cache convergence. If thresholds fail, the authorized operator moves the
   label back to the recorded approved version, or redeploys an explicit pin.
   Verify resolution across instances; do not create a new wording version and
   call that a rollback.

No promotion, label mutation, or hosted evaluation runs are performed by the
assets. Keep write credentials out of serving processes where feasible.

## Privacy and telemetry

Only reviewed templates belong in prompt management: no secrets, retrieved
documents, customer messages, personal identifiers, or credentials in prompt
names, labels, configuration or saved versions. Runtime variable values must
not become prompt-management records. Treat evaluation datasets, expected
outputs, scores, judge inputs and annotations as a separate data-export
decision with consent, minimization, access, residency, retention and deletion
controls. Prefer synthetic/redacted fixtures; do not upload production traces
into datasets automatically. Online scoring is not permission to export text.

`PreparedPrompt.trace_metadata()` returns only selector kind and the numeric
resolved version. Bind that to a reviewed operation identity in the consumer;
add other accounting fields only from the
[existing allowlist](accounting-and-observability.md).
Never pass rendered messages, variable mappings, raw SDK results or exception
bodies to a trace. Do not attach the full prompt object to a generation under
a metadata-only policy. Disable automatic function-argument, return-value and
provider content capture; test the actual exported payload.

SDK exceptions are suppressed in formatted tracebacks, not erased from process
memory. Disable traceback-local capture and exception-context introspection in
exporters. Keep unexpected programming errors visible locally without exporting
their values. Langfuse masking can redact exported attributes; the documented
Python export-stage `mask_otel_spans` hook covers spans exported by that client,
not every exporter in the process. Masking is defense in depth, not a substitute
for disabling capture or authorization to store content.

## Verification and limits

Run the copied test module with pytest in the consumer's project. It exercises
pins, mutable-label promotion and rollback, selector validation, rendering,
metadata allowlisting, shape rejection and privacy-safe fetch errors without a
network. It verifies required TTL configuration, strict integer TTL/version
validation and TTL forwarding, not real cache timing, service availability,
SDK compatibility, content quality, masking configuration, or live rollout.
Verify those separately against the pinned SDK and approved infrastructure.

## Primary sources

- [Get started: chat fetch, raw prompt and compilation](https://langfuse.com/docs/prompt-management/get-started)
- [Version control: identifiers, mutable labels and missing-label behavior](https://langfuse.com/docs/prompt-management/features/prompt-version-control)
- [Caching: TTL, background refresh, misses and explicit fallback](https://langfuse.com/docs/prompt-management/features/caching)
- [Masking: export-stage privacy boundary](https://langfuse.com/docs/observability/features/masking)
- [Evaluation: datasets, experiments, scores and the evaluation loop](https://langfuse.com/docs/evaluation/core-concepts)
