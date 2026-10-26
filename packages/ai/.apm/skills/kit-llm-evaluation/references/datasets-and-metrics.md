# Datasets and metrics

Reviewed 2026-10-23.

## Golden datasets

A golden dataset is a versioned, reviewed file of cases with expected
properties. Treat it like code: changes go through review, and every result is
reported against an exact version and content digest.

| Property | Rule |
| --- | --- |
| Identity | Stable case ids; a changed case gets a new id, never a silent edit |
| Version | Immutable label (`eval-v3`) plus the harness `sha256:` fingerprint |
| Provenance | Every case has `source`: `synthetic`, `incident-redacted`, `expert-written`, `public:<license>` |
| Coverage | Tags for normal, paraphrase, edge, adversarial, must-refuse and no-answer slices |
| Held-out split | A slice never used while iterating on prompts; touched only for release decisions |
| Size | Enough cases that the minimum detectable difference is below the change you care about |
| Ownership | One owner approves additions and removals and records why |

Grow the set from failures: when online signals or incidents reveal a gap, add
a redacted or synthetic case and re-run the baseline before comparing.
Do not delete failing cases to pass a gate; mark them invalid with a reason.

The [JSONL example](../assets/golden_dataset.jsonl.template) shows the harness
schema. Keep expected values short and checkable; put long references in a
separate file keyed by case id.

## Offline and online evaluation

| Mode | Data | Runs when | Purpose | Gate? |
| --- | --- | --- | --- | --- |
| Unit tests with fakes | Scripted outputs | Every commit | Client and error handling behave | Yes |
| Offline evaluation | Golden dataset, real model | Prompt, model, parameter or retrieval change; scheduled | Quality versus a baseline | Yes, in CI or release |
| Online evaluation | Sampled live traces | Continuously after release | Drift, new failure modes | Alert, then re-run offline |
| Human review | Stratified sample | Launch, rubric calibration, disputes | Ground truth | Decision input |

Online scores are signals, not proof of regression: traffic mix changes.
Never copy production traces into a dataset automatically.

## Metrics catalogue

Prefer the cheapest deterministic metric that captures the requirement.

| Metric | Use for | Implementation | Caveat |
| --- | --- | --- | --- |
| Exact match | Labels, identifiers, short answers | Normalize case and whitespace, compare | Penalizes harmless format variation |
| Fuzzy match (token F1, edit distance) | Short free text | Token overlap or normalized distance | Rewards lexical overlap, not meaning |
| Schema validity | Structured output | Validate with the same typed model as production | Valid shape is not correct content |
| Field-level accuracy | Extraction | Per-field comparison after validation | Report per field, not only overall |
| Task-specific checks | Totals, dates, citations exist, length limits | Code | Cheap and reliable; write these first |
| Refusal and no-answer rate | Must-refuse and unanswerable slices | Label or judge | Track over-refusal on must-answer cases too |
| LLM-as-judge with rubric | Tone, helpfulness, faithfulness | Pinned judge, versioned rubric, JSON verdict | Requires calibration; see [judges](judges-and-statistics.md) |
| Pairwise preference | Comparing two candidates | Judge or humans pick A, B or tie, both orders | Gives relative, not absolute, quality |
| Latency p50/p95 and cost per case | Every run | Recorded from the client port | Gate like quality |

### Retrieval-augmented generation

Retrieval metrics (recall at k, reciprocal rank, no-evidence accuracy,
permission leaks) belong to the `kit-retrieval` skill and its evaluation
reference. Measure the answer stage here:

| Metric | Question | Needs |
| --- | --- | --- |
| Faithfulness (groundedness) | Is every claim supported by the retrieved context? | Answer, context; claim extraction plus judge |
| Answer relevance | Does the answer address the question? | Question, answer |
| Context precision | Are the retrieved chunks ranked relevant first? | Question, ranked context, reference or judge |
| Context recall | Does the context contain what the reference answer needs? | Context, reference answer |

Report the four separately. A faithful answer built on wrong context and a
relevant answer with unsupported claims are different defects with different
fixes. Library implementations differ in prompts and formulas; pin the library
version and record it as part of the scorer version.

## Red-teaming and safety evaluations

- Keep an adversarial slice: prompt injection in user content and retrieved
  documents, requests for system prompts or secrets, policy-violating
  requests, jailbreak paraphrases, and tool-misuse attempts for agents.
- Gate must-refuse cases on refusal rate and must-answer cases on
  over-refusal; both directions matter.
- Map cases to a published taxonomy (OWASP Top 10 for LLM applications) so
  coverage gaps are visible.
- Treat red-team prompts as sensitive: store them with restricted access and
  never publish working exploits in shared datasets.
- Automated red-team generators supplement, but do not replace, reviewed cases.

## Privacy of evaluation data

- Prefer synthetic or expert-written cases. Redact incident-derived cases and
  record the redaction in `source`.
- Evaluation datasets, outputs, judge inputs and annotations are data exports:
  apply consent, minimization, residency, retention and deletion controls
  before sending them to a hosted evaluation service or a judge provider.
- Reports carry metrics, ids and digests, not inputs or outputs; the harness
  report is content-free by design.
- Delete a case everywhere (dataset, hosted copy, cached outputs) when its
  source must be deleted.

## Primary sources

- [Langfuse datasets](https://langfuse.com/docs/evaluation/experiments/datasets)
- [OpenAI evaluation best practices](https://platform.openai.com/docs/guides/evaluation-best-practices)
- [Anthropic: define success criteria and build evaluations](https://docs.anthropic.com/en/docs/test-and-evaluate/develop-tests)
- [Ragas metrics overview](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)
- [OWASP Top 10 for LLM applications](https://genai.owasp.org/llm-top-10/)
- [NIST AI 600-1 Generative AI profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence)
