---
name: kit-consistency
description: Use when finding mismatched contracts, terminology, defaults, or behavior across related files.
license: MIT
---

# Check consistency across a change

## Procedure

1. List the canonical source for each changed name, value, schema, and default.
   If two sources claim the same concept, decide which wins before editing.
2. Search callers, serializers, docs, configuration, fixtures, and generated references,
   including string-based lookups that symbol search misses.
3. Compare the same concept at each boundary: spelling, nullability, units, time zone,
   allowed values, defaults and error meaning. Record it in the
   [contract matrix](assets/contract-matrix.md.template) using the column guide in
   [contract matrices](references/contract-matrices.md).
4. Distinguish intentional compatibility aliases from accidental duplicate sources of truth.
5. Update the canonical definition first, then regenerate derived artifacts, then its
   owned consumers in one coherent change.
6. Preserve wire formats and persisted values unless migration behavior is explicit.
7. Check names against the project's conventions
   ([naming conventions](references/naming-conventions.md),
   [naming policy worksheet](assets/naming-policy.md.template)):
   - files and directories: [`check_naming.py`](assets/check_naming.py)
     (`python check_naming.py . --kebab-root docs`);
   - classes vs module files: [`check_class_file_naming.py`](assets/check_class_file_naming.py)
     (`python check_class_file_naming.py src --match affix`), with layout rules in
     [module layout](references/module-layout.md).
8. Keep public names on one canonical import path; make helpers private and
   re-export deliberately.
9. Add a test that crosses the boundary where drift would become observable.
10. Check that examples and negative cases agree with the actual accepted contract.
11. Do not mass-rewrite unrelated wording or normalize independently owned files;
    roll out a new naming rule from a counted baseline with dated exemptions.
12. Summarize any known intentional differences rather than silently erasing them.

## Acceptance gates

- Every row of the contract matrix has a canonical owner and a test, or an explicit
  "not applicable" reason.
- Missing, null, empty and unknown-enumeration inputs have deliberate, tested outcomes.
- Generated derivatives were regenerated from the canonical source, not hand-edited.
- `check_naming.py` and `check_class_file_naming.py` report no new findings
  against the agreed baseline, and every exemption names a reason.
- Renamed public modules or fields keep a compatibility path or a documented break.

Name checks prove spelling and placement only; semantic equality still needs
the boundary tests. Start with the [boundary comparison](references/guide.md).
