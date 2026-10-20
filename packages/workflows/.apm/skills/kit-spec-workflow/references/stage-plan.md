# Stage 4: Plan

Plan decides how the requirements will be met and breaks the work into tasks
small enough to finish, review and verify one at a time.

## Entry criteria

- `Status: specified` and the checker passes for requirements.
- The implementer has read the affected code paths and their tests.

## When a design document is required

Write [design.md](../assets/design.md.template) when any of these hold:

- The change crosses a module, service, package or team boundary.
- A public contract, persisted data shape or migration changes.
- There are at least two credible implementation options.
- Security, privacy, performance or availability properties change.
- Rollback needs more than reverting the commit.

Otherwise a short "Approach" paragraph at the top of `tasks.md` is enough.

## Design activities

1. Describe the current state in a few sentences with file paths.
2. Record each decision as: context, options considered, choice, consequences.
3. Show the data or call flow for the main scenario (a numbered list is fine;
   a diagram is optional).
4. List contract changes with compatibility handling, and the migration order
   (expand, migrate, contract) for data shape changes.
5. State how each non-functional requirement will be measured.
6. Note what the design intentionally leaves out, to stop gold-plating.

## Task activities

1. Copy [the tasks template](../assets/tasks.md.template) to `tasks.md`.
2. Group tasks under headings by deliverable (contract, storage, service,
   interface, documentation, rollout). Headings are optional; checkboxes are
   not.
3. Write each task as `- [ ] N.M <verb> <object> (REQ-NNN)`. A task:
   - fits in one focused session and one reviewable diff;
   - names the requirement identifiers it serves;
   - ends in an observable result (a passing test, a migrated table, a doc
     page) rather than an activity ("investigate", "look at").
4. Put test tasks before or alongside the implementation task they guard.
5. Add explicit tasks for documentation, configuration, telemetry and rollout
   switches named in the proposal's impact list.
6. Order tasks so the system stays releasable after each one: additive
   contract changes first, consumers next, removals last.
7. Run the checker with `--trace`; every active requirement must be cited by
   at least one task. Set `Status: planned`.

## Exit criteria

- Design decisions are recorded where a design is required.
- Every task is a checkbox, cites requirements and has an observable result.
- Every active requirement is covered by at least one task.

## Acceptance gate

```text
python assets/check_spec_change.py <changes>/<id> --trace
```

exits 0 (a missing `verification.md` is expected and not checked until the
status reaches `verified`). Continue with [apply](stage-apply.md).

## Anti-patterns

- Tasks named after files ("edit service.py") instead of outcomes.
- A final "write tests" task that collects all testing at the end.
- Plans that leave the main branch not releasable for several tasks.
- Designs that restate the requirements instead of deciding anything.

## Sources

- [Python unittest documentation](https://docs.python.org/3/library/unittest.html)
- [GitHub task lists in Markdown](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/about-tasklists)
