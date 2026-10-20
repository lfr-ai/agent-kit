---
description: Evaluate a retrieval pipeline on a versioned golden set for recall, no-evidence accuracy, and access filtering, and gate it against a baseline.
argument-hint: Pipeline or change to evaluate, e.g. "hybrid search with re-ranking"
agent: agent
---

# Evaluate retrieval quality

Measure whether retrieval finds the right sources for the right users, and
whether a change made it better or worse. Similarity scores are not evidence
of correctness.

## Input

- The user-supplied argument names the pipeline, index, or change to
  evaluate. Ask for the location of the golden set if the repository does not
  contain one; never build it from production queries or personal data.

## Procedure

1. Load [kit-retrieval](../skills/kit-retrieval/SKILL.md) and follow its
   [evaluation guidance](../skills/kit-retrieval/references/evaluation.md).
2. Locate or create a versioned golden set with synthetic or approved data.
   Each case has a query, the principal or tenant, the expected source
   identifiers, and whether no answer is the correct outcome.
3. Make sure the set includes ordinary questions, paraphrases, multi-source
   questions, no-answer cases, and permission cases where the expected result
   is empty for an unauthorized principal.
4. Pin everything that affects results: embedding model and version, index
   build, chunking settings, filters, `top_k`, fusion and re-ranking settings.
5. Run the baseline configuration and record recall at k, mean reciprocal
   rank, no-evidence accuracy, and the permission leak count.
6. Run the candidate configuration with the same set and settings except the
   change under test.
7. Inspect failures by hand: which expected source was missed, at which stage
   (chunking, filtering, ranking, fusion), and why.
8. Confirm that filters run inside the store before ranking and that another
   tenant or an unauthorized principal receives nothing.
9. Gate the result: no permission leaks, and no metric below the recorded
   baseline by more than the agreed tolerance.
10. Record the result with the configuration so it can be reproduced.

## Acceptance gates

- [ ] Permission leak count is zero.
- [ ] No-answer cases return an explicit no-evidence result.
- [ ] Metrics are compared with a recorded baseline on the same set version.
- [ ] Queries and chunks are not logged beyond the retention policy.

## Output

A metrics table (metric, baseline, candidate, delta, gate), the failure
analysis by stage, the exact configuration and commands, and a recommendation
to adopt, revise, or reject the change.
