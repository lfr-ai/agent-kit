---
name: kit-infra-review
description: Use when reviewing infrastructure changes that span IaC, deployment scripts, containers, or CI to ensure safe, auditable outcomes.
license: MIT
---

# Infrastructure review

Coordinate a review across infrastructure layers, then judge the combined
risk. Detail for each layer lives in its specialist skill:
`kit-terraform-validation`, `kit-azure-validation`, `kit-ci-review`,
`kit-containers`, `kit-observability`, `kit-edge-networking`, and
`kit-remote-access`. Start with the
[review guide](references/guide.md).

## Procedure

1. Scope the change: environments, accounts or subscriptions, state
   backends or stacks, pipeline identities, data-bearing resources, and
   whether untrusted triggers can run it
   ([review procedure](references/review-procedure.md)).
2. Collect operator-produced artifacts (plan JSON, what-if JSON, workflow
   diffs, image digests and scan output, telemetry configuration) with their
   commands, tool versions, and SHA-256 checksums. Do not authenticate to
   production to create them.
3. Run each layer's mechanical check through its specialist skill:
   - Terraform: `review_plan.py --file plan.json` plus the static pipeline.
   - Bicep: `review_whatif.py --file whatif.json` plus build, lint, and
     `build-params`.
   - Workflows: `check_workflow_permissions.py` on changed workflows.
   - Images: Hadolint, digest pins, scan, SBOM, provenance.
   - Telemetry: collector validation and `promtool check rules`.
4. Stop on malformed artifacts (reviewer exit 2) and request regeneration;
   record non-zero results from well-formed input as findings.
5. Classify every resource change as destructive, access-widening,
   ownership change, supply-chain, operational, or benign, and record the
   approval each class requires.
6. Answer the cross-layer questions: pipeline identity privilege versus need,
   untrusted triggers on the apply path, telemetry and alerts for new
   resources, version bumps that change behavior without template diffs, and
   rollback feasibility for data-bearing resources. Classify reversibility
   and record restore points with [rollback and recovery](references/rollback-and-recovery.md).
   Check drift before trusting the plan, size the blast radius, and estimate
   the cost delta with [drift, blast radius, and cost](references/drift-blast-radius-cost.md).
7. Fill the [change-type worksheet](assets/templates/change-type-worksheets.md.template)
   section for each change type present (network and edge, identity, data,
   compute, pipeline, observability).
8. Apply the [acceptance gates](references/acceptance-gates.md) and decide:
   accept, accept with conditions (never for destructive or access-widening
   gaps), or reject.
9. Fill the [evidence record](assets/templates/infrastructure-evidence-template.md)
   and the [review report](assets/templates/review-report.md.template),
   including skipped checks with reasons.
10. Hand apply, deploy, and rollback to the named operator with the evidence;
    never apply during review. Escalate unresolved questions to the owners.

A read-only reviewer role for delegated reviews is defined in
[agents.json](assets/agents.json).

## Acceptance gates

- [ ] Artifacts are operator-produced with commands and checksums recorded.
- [ ] Every applicable layer check ran, or its skip is justified.
- [ ] Destructive changes carry owner approval and a recovery plan.
- [ ] Irreversible changes are named and explicitly accepted by the owner.
- [ ] Access-widening changes carry security owner approval.
- [ ] Supply-chain inputs are pinned (SHA, digest, or exact version).
- [ ] New resources are observable and alerted.
- [ ] Drift resolved before the plan; blast radius and cost delta recorded.
- [ ] Evidence record and review report are complete.
- [ ] A named operator owns apply and rollback.

## Out of scope

This review separates source validation from any action that mutates remote
infrastructure. It does not apply, deploy, import, move state, or rotate
credentials.
