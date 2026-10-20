---
name: kit-spec-workflow
description: Use when carrying a change specification from discovery through implementation and archival using the repository's installed tooling and process.
license: MIT
---

# Run a spec-driven change lifecycle

A change is one folder of Markdown files that moves through seven stages. Each
stage has entry criteria, work, exit criteria and an acceptance gate; never skip
a gate because the code "already works". The folder contract, status model and
naming rules are in the [lifecycle overview](references/lifecycle.md).

## Before you start

1. Read the consumer's contributing guide, existing living specs and open change
   folders. If the project already runs a spec tool, follow its commands and
   folder layout; use this skill's contract only where the project has none.
2. Choose one change identifier: kebab-case, verb first, one outcome
   (`add-invoice-export`, not `invoice-stuff`). One change, one folder, one
   reviewable outcome; split anything that needs two independent approvals.
3. Copy the templates you need from `assets/` into the change folder and keep
   the `TBD` markers until the content is real; the checker blocks on them.

## Stages

1. **Explore** - investigate the problem without committing to a solution.
   Follow [explore](references/stage-explore.md). Gate: a written problem
   statement, evidence, and a recommendation to propose, defer or drop.
2. **Propose** - fill [proposal.md](assets/proposal.md.template) with the why,
   scope, non-goals, impact and rollback. Follow
   [propose](references/stage-propose.md). Gate: an owner accepts the scope.
3. **Specify** - write testable requirements with Given/When/Then scenarios in
   [requirements.md](assets/requirements.md.template). Follow
   [specify](references/stage-specify.md). Gate: every active requirement has
   at least one scenario and uses a normative keyword.
4. **Plan** - write [design.md](assets/design.md.template) when the change
   crosses a boundary, then [tasks.md](assets/tasks.md.template) as small
   checkbox tasks that cite requirement identifiers. Follow
   [plan](references/stage-plan.md). Gate: the checker passes with `--trace`.
5. **Apply** - implement task by task, test first where practical, and tick a
   box only when its evidence exists. Follow [apply](references/stage-apply.md).
   Gate: all boxes ticked, or open ones explicitly deferred to a new change.
6. **Verify** - prove each scenario and record the outcome in
   [verification.md](assets/verification.md.template). Follow
   [verify](references/stage-verify.md). Gate: `Result: pass` with evidence for
   every scenario and no unexplained deviation from the design.
7. **Archive** - merge accepted requirements into the living spec, move the
   folder to the archive and set `Status: archived`. Follow
   [archive](references/stage-archive.md). Gate: the living spec and the
   archived folder agree, and the checker still passes.

Maintenance operations - sync a living spec mid-flight, update a change whose
scope moved, continue an interrupted change, archive several finished changes
at once - follow [operations](references/operations.md).

## Check the folder

Run the stdlib [checker](assets/check_spec_change.py) at every gate:

```text
python assets/check_spec_change.py <changes>/add-invoice-export --trace
```

It prints `path:line: message` per defect and exits 1 on findings (2 on
unreadable input). It verifies required files, requirement scenarios, normative
wording, checkbox-only task lists, requirement-to-task trace, status versus
open tasks and verification result, and unresolved `TODO`/`TBD`/`FIXME`/`XXX`
markers. Override names and markers with `--required`, `--spec-name`,
`--tasks-name`, `--marker` and `--id-pattern`. Run `--self-test` after editing
the checker.

## Acceptance gates

- [ ] The proposal states the problem, scope, non-goals and rollback.
- [ ] Every active requirement is testable and has at least one scenario.
- [ ] Every task is a checkbox that cites the requirement it serves.
- [ ] Each scenario maps to an automated test or a recorded manual check.
- [ ] Verification evidence is reproducible: exact commands and outcomes.
- [ ] The status line matches reality; the checker exits 0.
- [ ] Living specs reflect archived requirements; nothing is archived early.

## Stop and escalate

- The checker cannot pass without weakening a requirement: return to Specify.
- Implementation reveals a different problem: run the update operation; do not
  silently rewrite approved scope.
- Verification fails twice for the same scenario: reopen Plan with the
  evidence instead of patching around the test.

Use the [stage playbook](assets/templates/spec-stage-playbook.md) as a one-page
tracker and the [quality gates and failure modes](references/guide.md) when
reviewing someone else's change.
