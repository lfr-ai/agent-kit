# Stage 1: Explore

Explore turns a vague request into a problem that is worth specifying. It is
thinking time with evidence, not implementation time: nothing written here is
binding, and code produced here is a throwaway spike unless a later task adopts
it deliberately.

## Entry criteria

- A request, defect report, incident follow-up or idea exists in writing.
- Nobody has yet committed to a solution or an estimate.
- The explorer can read the relevant code, living specs and recent history.

## Activities

1. Restate the request in one sentence from the user's point of view. If you
   cannot, list the competing interpretations and ask the requester to pick.
2. Collect evidence: failing behavior, logs, support tickets, metrics, the
   current living spec and the code paths involved. Cite file paths and lines.
3. Map the blast radius: which modules, contracts, data stores and consumers
   would a change touch? A dependency graph query or a text search over
   imports is usually enough at this stage.
4. Sketch two or three candidate approaches, including "do nothing" and "change
   configuration only". Note the cost, risk and reversibility of each.
5. Run a time-boxed spike only to answer a specific question (for example
   "can the export stream rows without loading the month into memory?").
   Record the question, the answer and the throwaway location.
6. Identify unknowns that block specifying: missing owner decisions, external
   dependencies, legal or data-retention constraints, performance budgets.

## Outputs

Store notes in `notes/explore.md` inside the change folder:

- Problem statement (one paragraph) and who experiences it.
- Evidence list with links and observed versus expected behavior.
- Candidate approaches with trade-offs and a recommendation.
- Open questions, each with an owner who can answer it.

## Exit criteria

- The problem statement is agreed by the requester.
- The recommendation is one of: propose, defer (with a revisit trigger) or drop
  (with the reason recorded where the request lives).
- Every blocking question has an answer or an owner and date.

## Acceptance gate

A reviewer reading only `notes/explore.md` can explain the problem, why it
matters now, and why the recommended approach beats the alternatives. If the
recommendation is "propose", set `Status: draft` in a new `proposal.md` and
continue with [propose](stage-propose.md).

## Anti-patterns

- Writing production code during exploration and then "just finishing it".
- Exploring only the first idea; a single candidate is not a comparison.
- Treating a spike's happy-path success as proof of feasibility under load,
  failure or concurrency.
- Leaving questions without owners; they resurface during Apply as rework.

## Time box

Set the time box before starting (for example half a day for a contained
change). When it expires, either propose with the known unknowns listed as
risks, or stop and report what evidence is still missing.

## Sources

- [Python profiling and tracing documentation](https://docs.python.org/3/library/profile.html)
- [Git log documentation](https://git-scm.com/docs/git-log)
