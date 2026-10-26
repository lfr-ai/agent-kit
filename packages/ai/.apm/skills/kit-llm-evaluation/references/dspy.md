# Optional DSPy candidates

Use DSPy when measured prompt/program optimization warrants another dependency.
Keep the local harness as the gate of record; DSPy is not required to score
recorded outputs, run parameter sweeps or compare managed prompt versions.
Adoption belongs in the consumer's reviewed dependency lock, not this toolkit.

## One candidate boundary

The [input-only adapter](../assets/dspy_task.py.template) implements the existing
harness `Task` interface. Copy it as `evals/dspy_task.py` beside `evals/harness.py`.
It accepts an already initialized question/answer program, forwards only
`case.input` as `question`, and validates that `prediction.answer` is text.
Expected answers, tags and source stay in the harness, never in the candidate.

A consumer that has approved the SDK and configured its model can use:

```python
import dspy

from evals.dspy_task import DspyTask

program = dspy.Predict("question -> answer")
task = DspyTask(program=program)
```

The snippet does not initialize a model, fetch an artifact, optimize a program
or make a network call. Configure these separately with explicit credentials,
deadlines, token limits and permitted endpoints. A tool-using DSPy program
requires its own side-effect/permission review; the adapter is not a sandbox.
Programs with another signature need a small consumer-owned mapping, not
automatic field guessing or passing the full case as keyword arguments.

Candidate exceptions propagate without retries or fabricated answers. Missing
or non-text answers raise `InvalidPredictionError`; empty text remains a valid
scoring input. Offline tests use a fake program and the actual harness, not an
installed DSPy distribution. Run real SDK compatibility tests in the consumer.

## Keep optimization separate from acceptance

| Data split | Permitted use | Prohibited use |
| --- | --- | --- |
| Development/train | Examples, demonstrations, optimizer feedback | Reporting its score as independent evidence |
| Validation | Candidate selection and bounded tuning | Repeatedly relabeling it as a final holdout |
| Final holdout | One pre-declared acceptance comparison | Optimizer input, prompt examples or candidate selection |

Split by leakage unit, not just random row: related documents, users, sessions
and near-duplicates must remain together. Track split membership, provenance,
dataset content fingerprints and metric versions. DSPy examples used for
optimization may include labels; declare only `question` as input using
`with_inputs("question")`. That does not make training data independent evidence.
Keep final-holdout references outside the optimizer and candidate boundary.
This split policy is the toolkit's evaluation requirement, not an automatic
guarantee supplied by DSPy's `trainset`, `valset` or `devset` parameters.

1. Establish an unoptimized candidate on the same validation cases and metrics.
2. Choose a documented optimizer for the actual program and objective. Record
   its configuration, seed, dependency versions and trial limit before running.
3. Approve one aggregate budget covering candidate, optimizer/teacher, judge,
   retry, validation and repeated calls. A `max_trials` setting or finite Hydra
   sweep is not a token/currency ceiling. Enforce limits at the client boundary,
   and cancel further launches when exhausted.
4. Select using validation only. Freeze the chosen program, prompt/model
   identity and scoring implementation before evaluating the holdout.
5. Score through `run_task` and the same harness scorers as other candidates.
   Compare only reports with matching dataset fingerprints and scorer versions.
   Declare floors and regression tolerance explicitly; a scoring-only exit 0
   does not approve release.
6. Record quality deltas, variance, cost and p95 latency against the unoptimized
   candidate. Reuse a simpler prompt if optimization has no meaningful benefit.

## Artifact identity and trust

Record the original program source revision, signature, exact SDK/model versions,
optimizer configuration, split fingerprints, candidate-state SHA-256, metric
versions and dependency-lock digest. A saved program state is not a model
weight checkpoint, and an optimizer's prompt is not automatically a versioned
Langfuse prompt. If promoting to managed prompts, publish and evaluate an exact
resolved prompt version through the existing prompt-management boundary.

Prefer reviewed state-only serialization when sufficient. DSPy's whole-program
save/load can use executable Python serialization; never load an untrusted
pickle/cloudpickle program, run code from a model response or auto-download a
candidate from an arbitrary URL. Even state-only artifacts may contain sensitive
examples or prompts: review contents, license, export policy, access and retention.
Verify the artifact digest and compatibility before loading; rollback restores
the prior reviewed artifact and exact environment rather than optimizing again.

## Acceptance checks

- Fake-program tests prove input-only forwarding, exact-match score shape,
  invalid-output rejection and unchanged failure propagation.
- Consumer SDK tests prove the approved program signature and state roundtrip.
- Holdout exclusion, total call/cost limits and artifact identity are recorded.
- Baseline comparison uses the same dataset and scorer versions.
- No SDK install, optimization, export or hosted execution is implicit.

## Primary sources

- [DSPy module boundary](https://dspy.ai/current/api/modules/Module/)
- [DSPy Predict signatures](https://dspy.ai/current/api/modules/Predict/)
- [DSPy optimization controls](https://dspy.ai/current/api/optimizers/MIPROv2/)
- [DSPy evaluation](https://dspy.ai/current/api/evaluation/Evaluate/)
- [DSPy saving and loading](https://dspy.ai/current/tutorials/saving/)
- [DSPy load and pickle approval](https://dspy.ai/current/api/utils/load/)
