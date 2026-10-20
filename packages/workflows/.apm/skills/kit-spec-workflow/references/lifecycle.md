# Lifecycle overview

This reference defines the change folder contract that every stage relies on.
It is deliberately small: Markdown files, one status line, stable identifiers.
A project that already owns a spec tool keeps its own layout; map the stages
below onto it rather than running two processes side by side.

## Folder layout

```text
<changes-root>/
  add-invoice-export/          one active change
    proposal.md                why, scope, non-goals, impact, status
    requirements.md            requirement sections with scenarios
    design.md                  optional; required for cross-boundary changes
    tasks.md                   checkbox task list citing requirement ids
    verification.md            evidence per scenario and overall result
    notes/                     optional exploration notes and spikes
  archive/
    2026-03-14-add-invoice-export/
<specs-root>/
  invoicing.md                 living spec: accepted requirements per capability
```

`<changes-root>` and `<specs-root>` are consumer decisions (for example
`docs/changes` and `docs/specs`). Record them once in the project's
contributing guide so every contributor and agent uses the same paths.

## Status model

`proposal.md` carries exactly one `Status:` line. Allowed values, in order:

| Status | Meaning | Set when |
| --- | --- | --- |
| `draft` | Exploration is still open | The folder is created |
| `proposed` | Scope is written and awaiting acceptance | Propose exit criteria met |
| `specified` | Requirements and scenarios are complete | Specify gate passed |
| `planned` | Tasks (and design if needed) are ready | Plan gate passed |
| `applying` | Implementation is in progress | First task started |
| `verified` | All scenarios proven, `Result: pass` | Verify gate passed |
| `archived` | Merged into living specs and moved | Archive gate passed |

Status only moves forward through the gates, except through the update
operation in [operations](operations.md), which may move it back to `proposed`
or `specified` with a dated note explaining why.

The checker enforces the two transitions that are most often faked: `verified`
and `archived` require every task box ticked and a verification report whose
first `Result:` line says `pass`.

## Identifiers

- Change identifier: kebab-case, verb first, unique among active and archived
  changes once the date prefix is removed.
- Requirement identifier: `REQ-` plus three or more digits, unique within the
  change. Living specs may renumber on merge; the archive keeps the original
  identifier so evidence links stay valid. Projects that prefer another scheme
  pass `--id-pattern` to the checker.
- Task identifier: optional dotted numbers (`1.1`, `1.2`) for discussion; the
  checkbox itself is the contract.

## Requirement grammar

```markdown
## REQ-001 Export a month of invoices

Change: add
The service MUST export all invoices dated in the requested month as CSV.

### Scenario: Month with invoices

- Given two invoices dated in March
- When the user exports March
- Then the file contains a header row and two invoice rows
```

- A requirement is a level-two heading that starts with its identifier.
- `Change:` is `add` (default), `modify` or `remove`. A `remove` needs a
  `Reason:` line and no scenarios.
- Text before the first scenario is the statement and must contain an
  uppercase normative keyword (MUST, SHALL, SHOULD or MAY), interpreted as in
  RFC 2119 and RFC 8174.
- A scenario is a level-three heading `### Scenario: <name>` followed by step
  lines. Each scenario needs at least one `When` and one `Then`, may start with
  `Given`, and uses `And`/`But` only to continue a previous step.

## Roles

| Role | Responsibility |
| --- | --- |
| Author | Drives the change through every stage and keeps status honest |
| Owner | Accepts scope at Propose and the result at Verify |
| Reviewer | Reviews requirements, design and evidence; never self-approves |
| Implementer | Executes tasks; may be the author |

Small changes may combine roles, but the owner acceptance at Propose and Verify
must be recorded by someone other than the implementer when the project
requires independent review.

## Stage map

| Stage | Reference | Primary artifact | Gate evidence |
| --- | --- | --- | --- |
| Explore | [stage-explore](stage-explore.md) | `notes/` | Problem statement and recommendation |
| Propose | [stage-propose](stage-propose.md) | `proposal.md` | Owner acceptance |
| Specify | [stage-specify](stage-specify.md) | `requirements.md` | Checker passes for requirements |
| Plan | [stage-plan](stage-plan.md) | `design.md`, `tasks.md` | Checker passes with `--trace` |
| Apply | [stage-apply](stage-apply.md) | Code and tests | All boxes ticked with evidence |
| Verify | [stage-verify](stage-verify.md) | `verification.md` | `Result: pass` |
| Archive | [stage-archive](stage-archive.md) | Living spec | Spec and archive agree |

## Sources

- [RFC 2119: Key words for use in RFCs](https://www.rfc-editor.org/rfc/rfc2119)
- [RFC 8174: Ambiguity of uppercase vs lowercase in RFC 2119 key words](https://www.rfc-editor.org/rfc/rfc8174)
- [Gherkin reference](https://cucumber.io/docs/gherkin/reference/)
- [CommonMark specification](https://spec.commonmark.org/)
