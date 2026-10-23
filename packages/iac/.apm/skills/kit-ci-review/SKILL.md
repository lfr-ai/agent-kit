---
name: kit-ci-review
description: Use when reviewing CI workflow changes that affect triggers, permissions, or publishing steps to ensure least privilege and reproducible validation.
license: MIT
---

# Review CI workflows

Treat CI as an authorization boundary. A workflow change can grant write
access, release secrets, or execute untrusted code just as an application
change can. Start with the [review guide](references/guide.md).

## Procedure

1. List changed workflow files, reusable workflows, and composite actions. For
   each, record its triggers and whether a fork, a comment author, or another
   workflow can start it.
2. Run the [workflow checker](assets/check_workflow_permissions.py) on the
   changed files: `python check_workflow_permissions.py .github/workflows`.
   Pass `--trusted-owner` only for owners covered by written policy and
   `--allow-expression` only for prefixes proven safe. Record its output.
3. Map token scopes per job using
   [permissions and tokens](references/permissions-and-tokens.md). Confirm a
   top-level least-privilege block, job-level write grants, and `id-token:
   write` only where a cloud login or attestation happens.
4. Trace every `${{` expression that reaches a `run:` script, a script action,
   or a file path back to its context using
   [untrusted input](references/untrusted-input.md). Require `env:` mapping
   for any value an outside actor can influence.
5. For `pull_request_target`, `workflow_run`, and `issue_comment` triggers,
   confirm no step checks out, installs, builds, or executes code from the
   triggering pull request, and that artifacts from untrusted runs are treated
   as data.
6. Verify supply-chain controls with [supply chain](references/supply-chain.md):
   full-SHA pins with version comments, digest-pinned containers, Dependabot
   coverage, lockfile-keyed caches, `persist-credentials: false`, and
   provenance attestations for published artifacts. Use the
   [zizmor policy template](assets/templates/zizmor.yml.template) as
   `.github/zizmor.yml` for a 14-day version-update cooldown; SHA pinning uses
   zizmor's default policy.
7. Confirm publish and deploy jobs depend on validation through `needs:`, run
   only on protected refs or tags, bind to protected environments, and use OIDC
   with narrow subject claims instead of stored cloud secrets.
8. Check bounds with [operations](references/operations.md): job timeouts,
   bounded matrices, superseded-run cancellation for pull requests, and
   non-cancelling deployment concurrency.
9. Confirm required checks keep stable job names and cannot be skipped into a
   passing state by `if:` conditions or path filters.
10. When proposing a new or rewritten workflow, start from the
    [hardened CI template](assets/templates/ci.yml.template), the
    [reusable build template](assets/templates/reusable-build.yml.template),
    the [dependency audit template](assets/templates/dependency-audit.yml.template),
    and the [Dependabot template](assets/templates/dependabot.yml.template).
11. Record publishing permissions and approvals in the
    [permission record](assets/templates/ci-permissions-template.md) and
    produce a findings list ordered by severity with file and line.
12. Never validate by triggering privileged workflows, re-running deploys, or
    using production credentials. Hand any rotation or settings change to the
    repository owner.

## Acceptance gates

- [ ] Checker exits 0 on the changed workflows, or every remaining finding has
      a written, owner-approved exception.
- [ ] Top-level `permissions:` exists in every workflow; no `write-all`.
- [ ] Every external `uses:` is a full commit SHA or an `@sha256:` digest.
- [ ] Pull requests run dependency review; the full lock is audited before
      installation and on a schedule.
- [ ] No untrusted context is expanded inside `run:` or script-action source.
- [ ] Privileged triggers never execute pull request code.
- [ ] Publish and deploy jobs use protected environments and OIDC.
- [ ] Every job has `timeout-minutes`; deploys do not cancel each other.
- [ ] Findings, exceptions, and owner approvals are recorded.

## Out of scope

Approving a workflow does not approve the release it produces. A clean checker
run is a mechanical precondition; it does not prove a pinned SHA is benign or
that repository settings match the file.
