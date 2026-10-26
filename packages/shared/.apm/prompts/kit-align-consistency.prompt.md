---
description: Find and fix drift in names, defaults, units, and error meaning for one concept across code, configuration, docs, and tests.
argument-hint: The concept or contract to align, e.g. a field, setting, or status value
agent: agent
---

# Align one concept across its boundaries

Make every producer, consumer, document, and test agree on one concept, with a
single canonical source.

## Input

- The user-supplied argument names the concept: a field, enum, setting,
  route, error code, or term. When it is empty, ask which concept to align;
  do not normalize the whole repository.

## Procedure

1. Load [kit-consistency](../skills/kit-consistency/SKILL.md) and use its
   contract matrix and naming checkers.
2. Find the canonical definition. If two places both claim it, stop and report
   the conflict with both locations before editing.
   Choose ownership by shared meaning and lifecycle, not matching spelling;
   use the [centralization/layout guide](../skills/kit-consistency/references/module-layout.md)
   for helper placement, filenames, grouping and subfolder decisions.
3. Search every use: symbol references plus string lookups in serializers,
   configuration, fixtures, migrations, docs, and generated files.
4. Fill one matrix row per boundary: spelling, type, nullability, units, time
   zone, allowed values, default, and error meaning. Mark each cell as agree or
   drift with a `path:line`.
5. Separate intentional compatibility aliases from accidental duplicates.
   Keep aliases that serve a real old consumer and record their removal step.
6. Fix in order: canonical definition, then regenerate derived artifacts, then
   owned consumers, then docs and examples. Never hand-edit generated output.
7. Leave persisted values and wire formats unchanged unless the user approved
   a migration; otherwise report the drift as a follow-up.
8. Add one test at the boundary where the drift would become observable.
9. Run the naming checkers on touched paths and the affected tests.

## Acceptance gates

- [ ] One canonical owner per concept, named in the report.
- [ ] Missing, null, empty, and unknown values have tested outcomes.
- [ ] No unrelated wording or independently owned files were rewritten.
- [ ] Every remaining difference is listed as intentional with a reason.

## Output

The contract matrix as a Markdown table, the changes made grouped by boundary,
commands run with results, and any drift deferred because it needs a migration
or owner approval.
