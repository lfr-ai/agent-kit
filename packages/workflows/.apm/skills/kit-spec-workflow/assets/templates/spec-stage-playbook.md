# Specification stage playbook

One-page tracker for a single change. Copy it into the change folder as
`notes/playbook.md` or into the review description, and tick each gate as the
evidence lands.

Change identifier: `<change-id>`

## 1. Explore

- [ ] Problem restated in one user-facing sentence
- [ ] Evidence collected with file paths, logs or metrics
- [ ] At least two candidate approaches compared, including doing nothing
- [ ] Recommendation recorded: propose, defer or drop

## 2. Propose

- [ ] Why, what changes, non-goals written
- [ ] Impact classified breaking or compatible
- [ ] Rollback executable by someone else
- [ ] Owner accepted scope (name, date)

## 3. Specify

- [ ] Each proposal bullet maps to at least one requirement
- [ ] Each requirement has a normative keyword and ordinary, boundary and
  failure scenarios where they apply
- [ ] Checker passes for proposal and requirements

## 4. Plan

- [ ] Design written when the change crosses a boundary or contract
- [ ] Tasks are checkboxes with requirement identifiers and observable results
- [ ] Checker passes with `--trace`

## 5. Apply

- [ ] Each task test-first where practical; evidence appended on tick
- [ ] Deviations recorded in the design
- [ ] Out-of-scope work moved to follow-up changes

## 6. Verify

- [ ] Each scenario has a verification row at an identified revision
- [ ] Full suite and non-functional targets recorded
- [ ] `Result: pass` and owner acceptance

## 7. Archive

- [ ] Living spec merged by change kind
- [ ] Folder moved to the dated archive path
- [ ] Checker passes on the archived folder

## Evidence checklist

- Checker command and exit code at each gate
- Review links for scope and result acceptance
- Test commands with revision identifiers
- Living spec diff at archive
