# Large refactorings: strangler fig, branch by abstraction, parallel change

Some structural changes are too large for one reviewable step: replacing a
subsystem, swapping a persistence layer, splitting a module used everywhere.
These patterns keep the system releasable at every step, so the change can
pause, ship partially, or be abandoned without a long-lived branch.

## Choosing a pattern

| Situation | Pattern |
| --- | --- |
| Replace a whole subsystem or application reachable through an entry point (routes, commands, messages) | strangler fig |
| Replace a component used from many places inside one codebase | branch by abstraction |
| Change an interface (function signature, schema, API field) with many callers | parallel change (expand, migrate, contract) |
| Change a stored data format | parallel change with dual write and backfill |

All of them prefer many small merged steps over one long-lived branch.

## Strangler fig

Grow the new implementation around the old one and move traffic over piece by
piece until the old one can be removed.

1. **Put a routing point in front** of the old system: a router, a command
   dispatcher, a message consumer, a facade function. At first it forwards
   everything to the old system.
2. **Pick a thin slice** (one endpoint, one command, one message type) with
   clear inputs and outputs and characterization tests around it.
3. **Implement the slice in the new system** and route only that slice to it.
   Keep a switch that can route it back.
4. **Compare** where possible: shadow-run the new path on the same input and
   log differences without serving them, then switch.
5. **Repeat** slice by slice. Track which slices are migrated in one visible
   list.
6. **Remove the old implementation** of each migrated slice once the switch has
   been stable, and finally remove the routing point if it no longer adds value.

Risks: shared data written by both systems (decide one writer per entity),
slices that are not really independent, and a migration that stalls with two
systems running forever. Set an explicit end condition.

## Branch by abstraction

Replace a component in place, on the main branch, behind an abstraction.

1. **Introduce an abstraction** (an interface, a protocol, a module-level
   function) that captures how callers use the component today.
2. **Move callers** to the abstraction one at a time, with the old
   implementation behind it. Each step is merged and released.
3. **Write the new implementation** behind the same abstraction, tested with
   the same contract tests as the old one.
4. **Switch** callers to the new implementation, all at once by configuration
   or gradually by caller. Keep the old one available for rollback.
5. **Delete** the old implementation, and the abstraction too if it only
   existed for the migration.

Contract tests are the key artifact: one test suite, parameterized over both
implementations, proves they are interchangeable.

## Parallel change (expand, migrate, contract)

Change an interface without breaking callers at any point:

1. **Expand**: add the new form beside the old one. A new function, a new
   optional field, a new column. Old callers keep working.
2. **Migrate**: move callers or data to the new form, in as many steps as
   needed. For stored data, write both forms, backfill old records, then read
   the new form.
3. **Contract**: once nothing uses the old form, remove it. For published APIs
   this happens only after a documented deprecation period.

For databases this is the expand/contract migration: additive schema change,
dual write, backfill, switch reads, stop writing old, drop old. Each step must
be deployable and reversible on its own; the drop is the only irreversible one,
so it goes last and separately.

## Feature toggles in refactoring

A toggle that selects old or new implementation is a release tool, not an
architecture. Keep it short-lived:

- Default to the old path until the new path is verified.
- Test both states in CI while both exist.
- Record an owner and a removal date for every toggle.
- Remove the toggle and the losing path in the same change that makes the
  decision permanent.

## Progress and stop conditions

For every large refactoring keep a short plan with:

- the end state and how you will know it is reached,
- the migrated and remaining slices or callers,
- the rollback for the current step,
- a stop condition (for example: if two consecutive slices need changes to the
  shared data model, re-plan).

Use the [behavior ledger](../assets/behavior.md.template) for each merged step.

## Sources

- [Martin Fowler: Strangler Fig Application](https://martinfowler.com/bliki/StranglerFigApplication.html)
- [Martin Fowler: Branch By Abstraction](https://martinfowler.com/bliki/BranchByAbstraction.html)
- [Martin Fowler: Parallel Change](https://martinfowler.com/bliki/ParallelChange.html)
- [Martin Fowler: Feature Toggles](https://martinfowler.com/articles/feature-toggles.html)
- [Azure Architecture Center: Strangler Fig pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/strangler-fig)
