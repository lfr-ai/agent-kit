# Evaluate a harness before growing it

A harness is everything an agent reads or runs besides the model: `AGENTS.md`,
skills, roles, hooks and tools. Treat a change to it like code: measure, then keep
only what pays for itself.

## Evidence (checked 2026-11-02)

| Finding | Source |
| --- | --- |
| Context files did not generally raise task success and added over 20% inference cost | [arXiv 2602.11988](https://arxiv.org/abs/2602.11988) |
| Context strategy did not measurably move correctness (bounded to 10-15 points); agents fail on implementation skill, not missing repository facts | [arXiv 2607.27250](https://arxiv.org/abs/2607.27250) |
| Harness² refines a harness without ground-truth feedback; its gains were on professional non-coding benchmarks (up to 11.5 points on WorkBuddy-Bench) | [arXiv 2610.14224](https://arxiv.org/abs/2610.14224), [repository](https://github.com/google-research/harness2) |

So the value of a harness is guardrails, correct verify commands, conventions
and cost control. Repository overviews are the first thing to prune. Coding
tasks have tests, which Harness² does not use, so do not expect its reported
gains to transfer; automatic tuning is optional and always human-reviewed.

## Order of work

1. **Static budgets.** Keep always-on text, skill descriptions and bodies within
   the catalog limits. Measure per profile with the toolkit check, for example
   `agent-kit check --root . --json`.
2. **Context cost.** Run the harness against a baseline on replayable tasks with
   a scripted model: equal actions isolate the token ratio the harness adds.
3. **Prune.** Remove or shorten text with no observed effect. A smaller harness
   that holds the same pass rate is the better harness.
4. **Correctness.** Compare arms on a real model with hidden graders, several
   trials and held-out tasks. Report Wilson intervals and a paired sign test;
   fewer than six non-tied tasks cannot show a difference.
5. **Optional refinement.** Let Harness² propose edits on training tasks only,
   judge the result on held-out tasks, and adopt lessons through review.

## Example: pi-harness-lab

```powershell
uv run --locked harness-lab harness import-agent-kit --source <kit> `
  --skill kit-config-review --agents <kit>/AGENTS.md --output build/harness
uv run --locked harness-lab harness validate --for-refinement build/harness
uv run --locked harness-lab eval <experiment.toml> --scripted-provider scenarios/solve-suite.json
```

A toolkit harness (`AGENTS.md` plus four skills) measured a 1.09 token ratio
with identical scripted correctness: about 9% more context per run. That is the
cost to justify with step 4, not a quality result.

## Limits

- A scripted model proves the pipeline and cost, never model behavior.
- Paid runs need explicit consent, a spend cap and no production data.
- Refined harnesses must not edit skill references or assets unseen; review the
  diff like any other change.
