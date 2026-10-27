# Choose and evolve infrastructure-as-code tooling

Pick the tool that will own each resource, record why, and plan any
migration so that no resource is ever owned by two tools at once. This
procedure produces a decision record and a migration plan; it never
provisions, imports, or moves state. Version and lifecycle facts in the
references were verified in 2026-10; re-check them before a decision that
depends on them.

## Inputs

- The clouds, accounts, subscriptions, and projects in scope, and who owns
  them (platform team, application team, or both).
- The tools already in use, with versions, state locations, and the number of
  resources each manages.
- Constraints: licensing policy, regulated data, hosted-service restrictions,
  team languages, existing CI system, and the policy engines already enforced.

## Procedure

1. Inventory what exists before proposing anything. For each tool record the
   version, state location (backend, stack service, deployment history), who
   can apply, and the resource count. Note any resource created by hand.
2. Separate the decision into layers: organization and landing zone,
   shared platform (network, identity, logging), and workload stacks. Each
   layer can use a different tool; each resource has exactly one owner. See
   [multi-cloud patterns](iac-multi-cloud-patterns.md).
3. Score candidate tools against the criteria in the
   [decision guide](iac-decision-guide.md): team skills, cloud
   coverage, state ownership, policy integration, licensing, ecosystem, drift
   handling, preview quality, and operating cost. Use the
   [tool matrix template](../assets/templates/iac-tool-matrix.md.template) so every candidate
   is scored on the same rows.
4. Eliminate tools that fail a hard constraint (license policy, end of
   support, missing cloud coverage, no supported preview). Do not select a
   retired tool for new work; Google Cloud Deployment Manager is past end of
   support.
5. Choose the policy layer with
   [policy as code](iac-policy-as-code.md): what runs before merge
   (static scanners, linters), what runs on the plan or preview, and what the
   cloud enforces at the organization boundary. Prefer controls the cloud
   enforces for anything that must never happen.
6. If the choice changes an existing owner, write a staged plan from
   [migrations](iac-migrations.md): freeze, back up state, adopt by
   import or state conversion, prove a no-change preview, then retire the old
   owner. Never run two tools against the same resource in the same window.
7. Write the [decision record](../assets/templates/iac-decision-record.md.template) with
   context, options, scores, decision, consequences, exit plan, and the
   date facts were checked.
8. Hand over to the owning review skill: `kit-terraform-validation` (the
   `terraform` feature) for Terraform or OpenTofu plans,
   `kit-azure-validation` (the `bicep` feature) for Bicep and ARM what-if,
   `kit-delivery-pipelines` for promotion and OIDC deployment, and the
   cross-cutting review in `kit-infra-review`.

## Acceptance gates

- [ ] Every in-scope resource has exactly one named owning tool and state
      location; hand-made resources are listed with an adopt-or-delete action.
- [ ] Each candidate tool is scored on the same criteria, and eliminated
      options state which hard constraint they failed.
- [ ] Licensing, support status, and version facts carry a verification date.
- [ ] The preview mechanism (plan, what-if, change set, preview, diff) is
      named for each layer, and CI produces it before any apply.
- [ ] Policy is placed at three points: before merge, on the preview, and at
      the organization boundary.
- [ ] A migration, if any, has a no-change preview gate, a rollback path, and
      a date when the old owner loses write access.
- [ ] No abstraction layer hides cloud differences behind a lowest-common-
      denominator module.

## Out of scope

This procedure does not deploy, import, convert state, or grant cloud access.
Plan and what-if review belong to the validation skills named above.
