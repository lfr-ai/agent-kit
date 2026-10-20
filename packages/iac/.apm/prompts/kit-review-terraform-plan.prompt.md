---
description: Review an operator-produced Terraform plan JSON read-only for deletes, replacements, drift, and access widening, producing an evidence bundle.
argument-hint: Path to the plan JSON and the root module or environment
agent: agent
---

# Review a Terraform plan

Decide whether a saved plan is safe to hand to the operator for apply. This
review is read-only: never run `apply`, `destroy`, `import`, or state commands,
and never create a plan with live credentials from this session.

## Input

- The user-supplied argument gives the plan JSON path (from
  `terraform show -json` on a saved plan) and the root module or environment.
  If no plan JSON exists, stop after the static checks and ask the operator to
  produce one.

## Procedure

1. Load [kit-terraform-validation](../skills/kit-terraform-validation/SKILL.md)
   and follow its procedure and exit-code meanings.
2. Identify the root module, environment, backend key, and workspace, and
   confirm the plan was produced from the commit under review.
3. Check configuration hygiene: version constraints, committed lock file,
   pinned module sources, provider blocks only in the root module, and one
   remote state with locking per environment.
4. Run the offline static checks the repository declares (format check,
   validate without a backend, tests, linters, security scan) or confirm CI ran
   them for this commit.
5. Run the skill's plan reviewer on the JSON. Treat an unreadable plan as a
   stop, not a pass.
6. For every delete or replace, read the action reason and decide whether it
   is intended. Data-bearing resources need an owner and a recovery plan.
7. Inspect resource drift, `moved`, `import`, and `removed` results, and any
   change to identity, network exposure, encryption, or access policy.
8. Confirm sensitive values are not printed and that the plan file is stored
   only where state may be stored.
9. Apply [kit-infra-review](../skills/kit-infra-review/SKILL.md) as well when
   the change also touches pipelines, scripts, or containers.

## Acceptance gates

- [ ] The reviewer exited cleanly, or every delete and replace has an owner
      and written decision.
- [ ] Drift and access-widening changes have a recorded decision.
- [ ] No state-changing command was run.
- [ ] Apply is handed to a named operator with the reviewed saved plan.

## Output

An evidence bundle: commit, plan checksum, reviewer summary (counts by
action), a table of risky changes (address, action, reason, decision), static
check results, and the operator handoff note.
