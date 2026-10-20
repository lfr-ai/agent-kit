---
description: Create a spec change folder with a proposal, testable requirements with scenarios, an optional design, and traced tasks that pass the checker.
argument-hint: Change identifier or a short description of the outcome
agent: agent
---

# Propose and specify a change

Turn an explored problem into an accepted, testable, planned change folder.
This prompt covers the propose, specify, and plan stages; it writes only
Markdown in the change folder, never product code.

## Input

- The user-supplied argument is a change identifier (kebab-case, verb first)
  or a description from which you derive one. Use exploration notes from the
  conversation when they exist.

## Procedure

1. Load [kit-spec-workflow](../skills/kit-spec-workflow/SKILL.md). Follow the
   project's own spec tool and layout when one exists.
2. Create one folder for one reviewable outcome; split anything that needs two
   independent approvals. Copy only the templates you need.
3. Propose: follow the [propose stage](../skills/kit-spec-workflow/references/stage-propose.md).
   Write why in user terms, what changes as observable bullets, non-goals,
   impact on contracts and data, risks, and rollback. Set the status to
   proposed and stop for owner acceptance of the scope.
4. Specify, after acceptance: follow the
   [specify stage](../skills/kit-spec-workflow/references/stage-specify.md).
   Write requirements with deliberate normative keywords and at least one
   Given/When/Then scenario each, using concrete values and outcomes that are
   observable from outside the unit.
5. Plan: follow the [plan stage](../skills/kit-spec-workflow/references/stage-plan.md).
   Add a design when the change crosses a boundary, then small checkbox tasks
   that each cite the requirement identifiers they serve.
6. Keep `TBD` markers until content is real; never fill them with guesses.
7. Run the skill's checker on the folder with `--trace` and fix every finding.

## Acceptance gates

- [ ] The proposal states problem, scope, non-goals, and rollback.
- [ ] Every proposal bullet maps to a requirement and every requirement has a
      scenario.
- [ ] Every task is a checkbox that cites a requirement.
- [ ] The checker exits 0 with `--trace`; the status reads planned.

## Output

The folder path and file list, the requirement-to-task trace as a table, the
checker result, and the owner decisions still needed. Offer the
`kit-spec-apply` prompt next.
