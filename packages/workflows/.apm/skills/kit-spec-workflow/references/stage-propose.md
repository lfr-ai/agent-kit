# Stage 2: Propose

The proposal is the contract about scope. It answers why the change exists,
what it will and will not do, who is affected and how to back it out. It does
not describe how the code will be written; that belongs in the design.

## Entry criteria

- Exploration recommended "propose", or the change is small and obvious
  enough that a reviewer agrees exploration is unnecessary.
- A change identifier has been chosen and the folder exists.

## Activities

1. Copy [the proposal template](../assets/proposal.md.template) to
   `proposal.md` and set `Status: draft`.
2. Write **Why** in user terms: the observed problem, who has it and the
   evidence. Link the exploration notes rather than repeating them.
3. Write **What changes** as a short list of observable behavior changes. Each
   bullet should later become one or more requirements.
4. Write **Non-goals**. Name the tempting adjacent work you are not doing; this
   is the main defense against scope creep during Apply.
5. Write **Impact**: affected capabilities, public contracts (APIs, events,
   file formats, CLI flags), data migrations, configuration, documentation and
   consumers. Mark each as breaking or compatible.
6. Write **Risks and rollback**: what can go wrong in production, how it would
   be detected, and the exact rollback (revert, flag off, migration down).
7. Name the **Owner** who accepts the scope and the **Reviewers**.
8. Set `Status: proposed` and request acceptance.

## Sizing rules

- One proposal, one outcome a user can observe. If "What changes" needs two
  unrelated headings, split into two changes.
- A breaking contract change needs its own requirement for the compatibility
  window (for example "the old field MUST remain readable for one release").
- If rollback is "restore from backup", the change needs a design and an
  owner sign-off on data risk before Specify.

## Exit criteria

- Owner acceptance is recorded in the proposal (name or handle and date) or in
  the linked review thread.
- Every impact item is classified breaking or compatible.
- Rollback is concrete enough that someone else could execute it.

## Acceptance gate

The checker passes for `proposal.md` presence and markers:

```text
python assets/check_spec_change.py <changes>/<id> --required proposal.md
```

and the owner has accepted the scope. Then continue with
[specify](stage-specify.md).

## Review questions

- Would a user notice each bullet in "What changes"? If not, it is a task.
- Is any non-goal actually required for the outcome to be useful?
- Does the impact list include docs, dashboards, alerts and runbooks?
- Can rollback run after data has been written in the new shape?

## Anti-patterns

- Proposals that describe classes and functions instead of behavior.
- "Improve performance" without a measurable target and baseline.
- Hidden breaking changes listed as "minor cleanup".

## Sources

- [Semantic Versioning 2.0.0](https://semver.org/)
- [RFC 2119: Key words for use in RFCs](https://www.rfc-editor.org/rfc/rfc2119)
