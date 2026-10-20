---
description: Explore a problem before committing to a solution, producing a problem statement, evidence, blast radius, candidate approaches, and a recommendation.
argument-hint: The request, defect, or idea to explore
agent: ask
---

# Explore a change before proposing it

Understand the problem well enough to recommend proposing, deferring, or
dropping it. Do not change product code; a time-boxed spike is allowed only to
answer one named question, and its code is thrown away.

## Input

- The user-supplied argument describes the request, defect, or idea. If it is
  empty, ask for it in one question.

## Procedure

1. Load [kit-spec-workflow](../skills/kit-spec-workflow/SKILL.md) and follow
   the [explore stage](../skills/kit-spec-workflow/references/stage-explore.md).
   If the project already runs its own spec tool, follow its commands instead.
2. Restate the request in one sentence from the user's point of view. If you
   cannot, list what is missing.
3. Read the living specs and any open change folders that touch the same
   capability, so you do not duplicate or contradict work in flight.
4. Collect evidence: observed versus expected behavior, logs, failing tests,
   metrics, and recent history of the affected files. Link each item.
5. Map the blast radius with
   [kit-graph-analysis](../skills/kit-graph-analysis/SKILL.md): modules,
   contracts, data stores, and consumers that a fix would touch.
6. Sketch two or three candidate approaches, including doing nothing, with
   trade-offs in effort, risk, and reversibility.
7. List unknowns that block specification, each with the person or system that
   can resolve it.
8. Propose a change identifier: kebab-case, verb first, one outcome.

## Acceptance gates

- [ ] The problem statement names who is affected and how.
- [ ] Every claim links to evidence you read.
- [ ] At least two approaches are compared, one of them doing nothing.
- [ ] The recommendation is one of propose, defer, or drop, with a reason.

## Output

Sections: Problem statement, Evidence, Blast radius, Approaches (table:
approach, benefit, cost, risk, reversible), Open questions with owners,
Recommendation, and the proposed change identifier. Offer to run the
`kit-spec-propose` prompt next when the recommendation is to propose.
