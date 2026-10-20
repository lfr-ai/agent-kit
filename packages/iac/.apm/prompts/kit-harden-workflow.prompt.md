---
description: Harden CI workflows with least-privilege tokens, SHA-pinned actions, safe handling of untrusted input, protected deploys, and job timeouts.
argument-hint: Workflow file or directory to harden
agent: agent
---

# Harden a CI workflow

Reduce what a compromised dependency, malicious pull request, or leaked token
could do, without changing what the workflow builds or publishes.

## Input

- The user-supplied argument names the workflow file or directory. When it is
  empty, use the workflow files changed in the working tree.

## Procedure

1. Load [kit-ci-review](../skills/kit-ci-review/SKILL.md) and follow its
   procedure.
2. List the workflows, reusable workflows, and composite actions in scope, and
   what each one triggers on, builds, publishes, or deploys.
3. Run the skill's workflow permissions checker on the target and record the
   baseline findings.
4. Set a restrictive top-level `permissions:` block and grant each job only
   the scopes it uses. Replace long-lived cloud secrets with OIDC federation
   where the provider supports it.
5. Pin every external action and container image to a full commit SHA or
   digest, with a comment naming the version; let the dependency bot update
   the pins.
6. Find every untrusted context expression (titles, branch names, bodies,
   inputs) that reaches a shell or script, and pass it through an environment
   variable instead of inline expansion.
7. Make sure privileged triggers such as `pull_request_target` and
   `workflow_run` never check out or execute pull request code.
8. Make publish and deploy jobs depend on validation, run in protected
   environments, and avoid cancelling each other through concurrency groups.
9. Add `timeout-minutes` to every job and keep required check names stable.
10. Re-run the checker and the repository's workflow lint. Never validate by
    triggering privileged workflows or re-running deploys.

## Acceptance gates

- [ ] The checker exits cleanly, or each remaining finding has an owner and a
      reason.
- [ ] No `write-all`, no unpinned external `uses:`.
- [ ] No untrusted context is expanded inside a script.
- [ ] Build and publish outputs are unchanged.

## Output

Before and after finding counts, a table of changes (workflow, job, change,
reason), remaining exceptions with owners, and commands run with results.
