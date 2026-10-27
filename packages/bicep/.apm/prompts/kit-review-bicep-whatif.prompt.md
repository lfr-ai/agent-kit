---
description: Review an operator-produced Bicep what-if JSON read-only for deletes, recreates, scope and access changes, and secrets, producing an evidence bundle.
argument-hint: Path to the what-if JSON and the entry template or environment
agent: agent
---

# Review a Bicep what-if preview

Decide whether a deployment preview is safe to hand to the operator. This
review is read-only: never deploy, never run what-if with live credentials
from this session, and never change role assignments.

## Input

- The user-supplied argument gives the what-if JSON path and the entry
  template or environment. If no what-if JSON exists, stop after build and
  lint checks and ask the operator to produce one with full resource payloads.

## Procedure

1. Load [kit-azure-validation](../skills/kit-azure-validation/SKILL.md) and
   follow its procedure and exit-code meanings.
2. Identify the entry template, its target scope, every scope its modules
   deploy to, and the parameter file per environment.
3. Confirm the templates build and lint, and that parameter files build for
   every environment, using the repository's pinned tooling.
4. Review modules for typed parameters, secure parameters for secrets, no
   secrets in outputs, and consistent names and tags.
5. Review identity and governance: managed identities, role assignments,
   policy exemptions, and network exposure.
6. Run the skill's what-if reviewer on the JSON. Treat an unreadable or
   incomplete preview as a stop, not a pass.
7. For each delete, recreate, or ignored change, decide whether it is
   intended. Data-bearing resources need an owner and a recovery plan.
8. Read every modify delta on identity, network, encryption, and access
   properties; list each widening of access explicitly.
9. Confirm CI authenticates with workload identity federation and that deploys
   run behind a protected environment.

## Acceptance gates

- [ ] Build, lint, and parameter builds pass for every environment.
- [ ] No secrets in parameter files or outputs.
- [ ] The reviewer exited cleanly, or each risky change has owner approval.
- [ ] Access changes are listed with a decision.
- [ ] Nothing was deployed by this prompt.

## Output

An evidence bundle: commit, scopes, parameter file, preview checksum, reviewer
summary (counts by change type), a table of risky changes (resource, change,
property, decision), and the operator handoff note.
