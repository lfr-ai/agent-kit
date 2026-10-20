# Risk register

A risk register lists what could go wrong with the change, how likely and how
bad it is, and what the plan does about it. It turns vague worry into slices,
tests, approvals and stop conditions. Keep it proportional: a local fix needs
one line or none; a migration touching shared data needs a table.

## Finding risks

Walk through the change with these prompts:

| Category | Prompt |
| --- | --- |
| Data | Can data be lost, duplicated, corrupted, or exposed? Is any step irreversible? |
| Compatibility | Which callers, stored formats, APIs or defaults could break? |
| Security | Does a trust boundary, permission check, secret or input parser change? |
| Operations | Does deployment order matter? Can old and new versions run side by side? |
| Performance | Do queries, loops or payload sizes grow with data volume? |
| Dependencies | New library, service, or version? Is it maintained and licensed for this use? |
| Knowledge | Which assumptions are unverified? Which component does nobody understand? |
| Delivery | Which step depends on someone else's approval, access or schedule? |

## Recording a risk

| ID | Risk | Likelihood | Impact | Response | Owner | Trigger / signal | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | Backfill writes duplicate invoices on retry | medium | high | make backfill idempotent by invoice number; test retry | backend owner | duplicate-key errors in the backfill log | open |
| R2 | CSV export memory grows with invoice count | high | medium | stream rows; test with 100 000 synthetic rows | slice 4 | memory above limit in load test | mitigated |
| R3 | Unknown whether the report consumer accepts a new column | medium | medium | spike: ask the consumer owner; keep column order | planner | consumer confirms or rejects | open |

- **Likelihood and impact**: low, medium, high is enough. Precise numbers
  suggest precision the team does not have.
- **Response**: one of
  - *avoid* (change the plan so the risk cannot occur),
  - *reduce* (a test, a validation, a toggle, a smaller slice),
  - *transfer* (an owner with the right access or expertise takes it),
  - *accept* (explicitly, with the reason and who accepted it).
- **Trigger / signal**: how you will notice the risk materializing, so the
  stop condition is concrete.

## Turning risks into plan changes

- High-impact risks get a dedicated slice early, a test that would fail if the
  risk materialized, or a spike that removes the unknown.
- Irreversible steps (dropping a column, deleting files, publishing) get their
  own slice, last, with an explicit approval and a backup or export first.
- Each high-impact risk has a matching entry in the
  [rollback plan](rollback-plan.md).
- Accepted risks are written into the hand-off so reviewers can disagree.

## Keeping it current

Review the register when a slice finishes, when new evidence appears, and
before any irreversible step. Close risks with the evidence that closed them
(test name, measurement, confirmation). A register that is never updated after
planning is decoration.

## Sources

- [NIST SP 800-30 Rev. 1: Guide for Conducting Risk Assessments](https://csrc.nist.gov/pubs/sp/800/30/r1/final)
- [OWASP Threat Modeling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html)
- [Google SRE workbook: canary releases](https://sre.google/workbook/canarying-releases/)
