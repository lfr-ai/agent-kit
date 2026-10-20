# Decompose work and draw ownership boundaries

Parallel work pays off only when the parts are genuinely independent. The cost
is coordination: briefing, waiting, reviewing, integrating. Decompose first,
then decide whether the result is worth parallelizing at all.

## Step 1: describe the outcome as checks

Write the observable outcome as a short list of checks that will be true when
the whole change is done, for example:

- `GET /orders/{id}` returns the stored order with its invoice total.
- The invoice service rejects negative line amounts with a validation error.
- The documentation page for orders lists the new field.
- The completion gate passes.

Each check later belongs to exactly one task. A check nobody owns is the usual
source of "everyone finished, nothing works".

## Step 2: find the seams

Split along boundaries the code already has, in this order of preference:

1. **Separate deployable units or packages** with their own tests.
2. **Separate modules behind a stable interface** (a function signature, a
   schema, a message format) that is already agreed and will not change.
3. **Separate file sets** inside one module where no file is written by two
   tasks.
4. **Read-only versus write**: research, review and test design can run beside
   any writer.

If the only available split is "models, then services, then tests", the work is
layered, not parallel. Sequence it as vertical slices instead (see the
change-planning skill if it is installed).

## Step 3: pin shared contracts first

Anything two tasks both depend on is a shared contract: a schema, an API shape,
a configuration key, a fixture, a dependency version, generated code. Before
starting parallel writers:

1. Assign the contract to one owner (usually the coordinator).
2. Land or write down the contract in its final form.
3. Give every worker the contract as read-only input.

A worker that discovers the contract must change stops and returns the
requested change to the coordinator. It does not edit the contract locally,
because a second worker is building against the old one.

## Step 4: write the ownership table

| Task | Writable paths | Read-only inputs | Prerequisite | Owner of check |
| --- | --- | --- | --- | --- |
| Orders API | `services/orders/**` | order schema v2 | schema merged | `GET /orders/{id}` |
| Invoice validation | `services/invoices/validation/**` | invoice schema | none | negative amounts rejected |
| Docs | `docs/orders.md` | API contract | none | docs page updated |
| Integration | dependency manifests, lockfile, generated clients | all | all tasks returned | completion gate |

Rules for the table:

- Writable path sets are disjoint. Use globs, and check overlaps for shared
  files such as `__init__.py`, barrel files, route registries, changelogs and
  lockfiles; these are the files most often edited by "independent" tasks.
- Files that every task wants to touch (lockfiles, dependency manifests,
  generated clients, changelog, registries) belong to the integration owner.
  Workers describe the needed edit in their return; the owner applies all of
  them once.
- Prerequisites are real data or code dependencies, not list order.
- Each task carries the same prohibitions: no remote pushes, deployments,
  global configuration changes or credential use unless the operator approved
  them for that task.

Copy the [bounded assignment](../assets/assignment.md.template) once per row.

## Step 5: size the tasks

- A task should be completable and verifiable without the others, and small
  enough that its diff can be reviewed in one sitting.
- Prefer two to five parallel writers. Beyond that, integration review becomes
  the bottleneck and conflicting assumptions multiply.
- Do not delegate a lookup that takes a few direct reads, or a single
  continuous trace through the code; the briefing costs more than the work.
- Workers do not delegate further. Nested delegation hides ownership.

## Anti-patterns

| Pattern | Why it fails | Instead |
| --- | --- | --- |
| Two workers "both fix the tests" | overlapping writes, duplicate fixes | one owner per failing area |
| Workers each bump a dependency | lockfile conflicts, inconsistent versions | integration owner bumps once |
| Contract decided during implementation | consumers build against a moving target | pin the contract first |
| Every worker runs the formatter over the whole tree | unrelated churn in every diff | format only owned paths; owner formats at the end |
| Worker silently widens scope to repair an unrelated failure | hidden edits outside ownership | report the failure; coordinator decides |

## Sources

- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [VS Code custom agents and subagents](https://code.visualstudio.com/docs/agent-customization/custom-agents)
- [Git worktree](https://git-scm.com/docs/git-worktree)
