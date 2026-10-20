# Vertical slices

A vertical slice is a thin, end-to-end piece of the change: from input through
every layer it needs to an observable result, with its tests. Each slice can be
merged, reviewed and (ideally) released on its own. The alternative,
horizontal layers ("all models, then all services, then the API, then tests"),
postpones integration until everything is written, which is where most defects
hide.

## Properties of a good slice

- **End to end**: touches every layer needed for one observable behavior, and
  no more.
- **Proves criteria**: names the acceptance criteria it satisfies and the test
  that proves each.
- **Small**: reviewable in one sitting; usually a few files and a few hundred
  changed lines at most.
- **Independent or explicitly ordered**: either it can be built in any order,
  or its prerequisite slices are listed.
- **Safe to merge**: the system works after merging it, even if the feature is
  incomplete (hidden behind a toggle, or simply not yet reachable).

## Slicing strategies

| Strategy | Example for "export invoices to CSV" |
| --- | --- |
| Simplest path first | export all invoices, no filters, fixed columns |
| By variation in input | add `--since` filter; add `--customer` filter |
| By variation in output | add currency formatting; add a totals row |
| By business rule | exclude cancelled invoices |
| By error path | reject invalid dates; handle an empty result |
| By interface | CLI first, then the HTTP endpoint reusing the same use case |
| By data volume | stream rows instead of building the file in memory |
| Spike, then slice | a time-boxed throwaway experiment to remove an unknown, then real slices |

The first slice is the **tracer bullet**: the thinnest path that connects every
layer and proves the architecture works. Later slices widen it.

## Ordering slices

1. Tracer bullet first.
2. Slices that remove the largest risk or unknown next (see
   [risk register](risk-register.md)).
3. Slices that unlock others (shared contract, migration expand step).
4. Remaining slices by value to the requester.
5. Clean-up slices last (remove toggles, old paths, contract step of a
   migration).

Record actual prerequisites, not list order. Two slices that touch disjoint
files with no shared contract can run in parallel (see the parallel-work skill
if installed).

## Writing a slice

Use the [slice template](../assets/slice.md.template). The essentials:

- Outcome in one sentence.
- Acceptance criteria covered, each with its test.
- Paths expected to change, and paths that must not.
- Prerequisite slices.
- The failing test written first, and the command that runs it.
- Rollback for this slice.
- Done when: the specific checks that close it.

## Signs a slice is wrong

| Symptom | Fix |
| --- | --- |
| It has no user-observable result | merge it into the slice that uses it, or reframe around a behavior |
| It touches every module | split by variation, rule or interface |
| It cannot be tested until another slice lands | reorder, or make the prerequisite explicit |
| Review keeps finding unrelated changes | cut the unrelated changes into their own slice or drop them |
| It needs a long-lived branch | add a toggle or an expand/contract step so it can merge early |

## Sources

- [Martin Fowler: Feature Toggles](https://martinfowler.com/articles/feature-toggles.html)
- [Martin Fowler: Parallel Change](https://martinfowler.com/bliki/ParallelChange.html)
- [Agile Alliance: INVEST](https://agilealliance.org/glossary/invest/)
- [The Pragmatic Programmer: tracer bullets (publisher page)](https://pragprog.com/titles/tpp20/the-pragmatic-programmer-20th-anniversary-edition/)
