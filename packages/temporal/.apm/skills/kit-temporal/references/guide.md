# Temporal runtime, verification and sources

Researched 2026-11-02 using unauthenticated public documentation and SDK source.
The package was empty apart from its manifest at inspection. No third-party
skill bodies, archives or license notices were present to preserve; these
instructions and templates are original, with links rather than vendored text.

## Runtime boundaries

Python is primary. TypeScript users should use the existing TypeScript codebase,
typed SDK APIs and its workflow-isolation rules; no JavaScript examples or new
toolkit dependency are needed. Bun may run a consumer's TypeScript checks, but
Temporal's TypeScript worker runtime is Node.js-supported: do not infer Bun
worker/native bridge compatibility from successful Bun tests. Verify the SDK's
supported runtime matrix before choosing a worker host.

Workflow commands must match recorded history during replay. Use workflow-safe
clock/random/UUID/timer APIs; stable iteration and deterministic concurrency
matter too. Imports and decorator execution can introduce nondeterminism even
when the run method looks pure. Use `workflow.unsafe.imports_passed_through`
only for reviewed deterministic modules. No workflow filesystem or environment
reads, HTTP callbacks, database access or model calls.

Activities may use typed keyword-injected Protocol collaborators and translate
vendor exceptions. Keep the framework decorators on thin adapter functions or
bound methods; domain policy needs no Temporal dependency. Activity retries do
not rerun completed workflow decisions; a timeout/lost response can rerun an
already committed external effect.

## Failure and operational contract

| Case | Required behavior |
| --- | --- |
| Permanent validation/permission failure | Non-retryable `ApplicationError`, safe type/code; test that no second effect occurs |
| Transient vendor outage | Bounded Activity retry and overall schedule-to-close budget; disable nested SDK retries or account for them |
| Attempt timeout / lost acknowledgment | Inspect destination by stable business key; never assume rollback |
| Long Activity | Heartbeat progress, poll/propagate cancellation; resume from durable destination state |
| Cancellation | Client/parent policy explicit; wait for cancellation where required; cleanup has its own bounded budget |
| Workflow task bug/nondeterminism | May repeatedly fail a Workflow Task rather than close execution; alert and deploy a replay-safe fix |
| Deployment change | Pinned runs keep old workers; Auto-Upgrade requires replay-safe patch/version strategy |

`execution_policy.py` raises `InvalidPolicyError` for nonpositive durations/attempts,
heartbeat not below the attempt timeout, attempt budget above total budget or
incoherent retry delays. It is preflight, not a simulator; queue time consumes
schedule-to-close, and that timeout may cut retries short.

Do not routinely set a short Workflow Execution timeout as a substitute for
business timers. Distinguish run/execution/task timeouts from Activity
start-to-close, schedule-to-close, schedule-to-start and heartbeat timeouts.
Schedule-to-start measures queue starvation and is not an ordinary retry lever.
Activity heartbeat cancellation delivery is cooperative; sync threads cannot be
assumed killed. Choose SDK cancellation type explicitly for side effects.

Use Worker Deployment Versioning rather than starting a new design on legacy
Build-ID routing. Pinned runs complete on a single deployment version; retain
workers until reachability/draining permits shutdown. Auto-Upgrade code must
remain replay-compatible, including patch branches and signal/update handlers.
Continue-As-New bounds history; carry business keys and necessary state into the
new run and coordinate outstanding handlers first.

## Verification ladder

1. Toolkit: run the two focused repo guard files with the existing interpreter.
   The stdlib policy tests exercise accepted/rejected timeout configurations and
   the pure Activity effect policy's first execution, committed-receipt reuse
   after a lost response, conflicting payload/key and blank-key rejection.
   `effect_policy.py.template` raises `InvalidEffectRequestError` for a blank
   business key and `IdempotencyConflictError` for a mismatched receipt. Use
   canonical payload bytes, and never log the payload or digest as a privacy
   workaround. The adapter must load the receipt and commit a same-destination
   effect/receipt atomically with uniqueness/concurrency control. For external
   effects, use provider idempotency/reconciliation; a local receipt alone cannot
   close the effect-committed/receipt-not-written window.
   The thin Activity adapter maps both policy errors to safe non-retryable
   `ApplicationError` types, preserving the cause with `from`.
2. Consumer: copy `test_temporal_behavior.py.template` without `.template`, then
   `python -m unittest -v test_temporal_behavior` using the already reviewed SDK.
   The time-skipping test environment starts a local test server and may download
   it. Pre-provision an approved binary for offline CI.
   Exact focused commands (documented, **not run here**):

   ```text
   python -m unittest -v test_temporal_behavior.TemporalBehaviorTests.test_retry_and_replay
   python -m unittest -v test_temporal_behavior.TemporalBehaviorTests.test_cancel_timer
   ```

3. Add ActivityEnvironment tests for injected vendor failures and heartbeat
   progress. Add a real test-server worker case that cancels a heartbeating
   Activity, proving cleanup and no extra effect. Cancel-before-start and
   timer cancellation are not evidence of running-Activity cancellation.
4. Persist sanitized representative old histories (retry, signals/updates,
   cancellation, patch branches, Continue-As-New); replay them with `Replayer`
   before promotion. The supplied same-code replay is only a smoke test, not
   upgrade certification. Add a deliberately incompatible fixture to prove
   the replay gate fails.
5. Test idempotency against the real destination: concurrent duplicate keys,
   effect-committed/response-lost, worker crash/restart and payload conflict.
   An in-memory set or an SDK syntax test proves none of these.

SDK/server, destination idempotency, heartbeat cancellation and deployment
runtime are **unverified in this toolkit**. No vendor runtime was installed or
test-server download performed.

## Security and LLM integration

Authenticate clients and workers with scoped credentials, TLS/mTLS or the
approved Cloud API-key mechanism. Limit namespace/task-queue access via the
actual platform authorization model; task queues are not an authorization
boundary by themselves. Authorize workflow-start, signal and update callers.
Never put tokens or secrets in workflow inputs, memo, Search Attributes,
exceptions or logs. History is durable; reference sensitive documents by
opaque IDs and fetch them only inside Activities. Configure payload encryption
and codec/key access where needed; it does not hide routing metadata, IDs or
Search Attributes. Retention and key rotation require an operator plan.

Invoke the existing LLM port from Activities, not workflow code. Recorded
Activity results replay without another model call, but an Activity retry may
still duplicate provider cost. Keep approval and destination idempotency at the
effect boundary. LangGraph checkpoints are not interchangeable with Temporal
history; choose one durable owner, and do not nest unbounded retry engines.

## Current documentation MCP

Official [Develop with AI](https://docs.temporal.io/with-ai) explicitly advertises
`https://temporal.mcp.kapa.ai` over HTTP with **MCP OAuth authentication**.
Confirmed from public docs on 2026-11-02; no credentials or authenticated MCP
session were used. A client must support MCP OAuth; anonymous tool access and
native-client compatibility were not tested. Parent owns MCP manifests/tables.
Do not add an invented `/mcp` suffix or confuse this documentation server with
Temporal's separate application MCP integration.

## Primary sources and SDK tests

- [Python SDK guide](https://docs.temporal.io/develop/python)
- [Python testing and replay](https://docs.temporal.io/develop/python/best-practices/testing-suite)
- [Activity timeouts and retry policies](https://docs.temporal.io/encyclopedia/detecting-activity-failures)
- [Worker Deployment Versioning](https://docs.temporal.io/production-deployment/worker-deployments/worker-versioning)
- [Python SDK API](https://python.temporal.io/)
- [Cloud security](https://docs.temporal.io/cloud/security)
- [TypeScript runtime requirements](https://docs.temporal.io/develop/typescript)
- Reviewed SDK main revision `c1a79fb659ffab144d7949213664a584809089f7`:
  [tests/worker/test_workflow.py](https://github.com/temporalio/sdk-python/blob/c1a79fb659ffab144d7949213664a584809089f7/tests/worker/test_workflow.py)
  exercises actual cancellation, retry and Replayer behavior;
  [tests/testing/test_workflow.py](https://github.com/temporalio/sdk-python/blob/c1a79fb659ffab144d7949213664a584809089f7/tests/testing/test_workflow.py)
  exercises time-skipping server behavior. These are behavioral precedents,
  not copied vendor test bodies or evidence that our templates ran.
