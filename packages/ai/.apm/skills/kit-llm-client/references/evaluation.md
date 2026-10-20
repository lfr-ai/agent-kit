# Evaluating model-backed features

Unit tests prove the client handles every outcome; evaluations measure whether
the model's outputs are good enough. Keep them separate: unit tests use the
scripted fake and run on every commit; evaluations call real models and run on
prompt, model or parameter changes and on a schedule.

## Evaluation set

- A versioned file of synthetic or approved inputs with expected properties:
  exact fields for extraction, labels for classification, rubric points for
  generation, and must-refuse cases.
- Cover edge cases from incidents after removing sensitive data, plus
  adversarial inputs such as embedded instructions in user content.
- Keep a held-out portion that is not used while iterating on prompts.

## Graders

| Grader | Use for | Caveat |
| --- | --- | --- |
| Exact or schema match | Extraction, classification, structured output | Strict; normalize formatting first |
| Programmatic checks | Totals, dates, references exist, length limits | Cheap and deterministic; prefer them |
| Model judge with a rubric | Free-text quality, tone, faithfulness | Pin judge model and prompt; calibrate against human labels |
| Human review | Launch decisions, rubric calibration | Slow; sample deliberately |

Run each case several times when temperature is above zero and report the
distribution, not a single sample. Do not claim deterministic behavior from a
temperature of zero.

## What to report

- Quality metric per grader with the case count.
- Structured-output validity rate and repair rate.
- Refusal rate on must-answer and must-refuse cases.
- Tokens, cost and latency percentiles per case.
- Prompt version, prompt fingerprint, model alias, served model, and
  parameters for the run.

## Gates

- A prompt or model change merges only with an evaluation run attached.
- Define tolerances per metric (for example no drop larger than two points in
  extraction accuracy, no increase in invalid output rate).
- Cost and latency are gated like quality; a cheaper model that fails quality
  gates is not cheaper.

## Online signals

After release, track structured-output failures, refusals, user corrections
and escalations per prompt version. A shift in these signals is a reason to
re-run the evaluation set, not proof of a regression by itself.

## Sources

- [OpenAI evaluation best practices](https://platform.openai.com/docs/guides/evaluation-best-practices)
- [Anthropic: define success criteria and build evaluations](https://docs.anthropic.com/en/docs/test-and-evaluate/develop-tests)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
