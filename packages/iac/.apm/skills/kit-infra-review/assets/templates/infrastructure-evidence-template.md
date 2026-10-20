Infrastructure Change Evidence Template

- Change ID / PR:
- Owner / operator:
- Intended account or subscription, backend key or scope, workspace or stack:
- Commit reviewed:

Artifacts provided (with checksums)

- plan.json: <sha256>  command: <terraform show -json ...>  terraform vX.Y.Z
- whatif.json: <sha256>  command: <az deployment ... what-if ...>  az/bicep vX.Y.Z
- workflow files: <paths>
- image: <registry/name@sha256:...>  SBOM: yes/no  provenance: yes/no
- telemetry config / alert rules: <paths>

Validator commands, versions, and exit codes

- review_plan.py --file plan.json: exit <n>
- review_whatif.py --file whatif.json: exit <n>
- check_workflow_permissions.py <paths>: exit <n>
- fmt / validate / test / lint / scan: <tool vX.Y> exit <n>
- hadolint / image scan: <tool vX.Y> exit <n>
- promtool check rules: exit <n>

Risk items (per resource)

- resource: class (destructive / access / ownership / supply-chain /
  operational), action, reason, mitigation or recovery, approver

Approval

- Approver: name, date, scope of approval

Rollback plan

- Steps to revert if apply or deploy fails, including data restore points

Notes and skipped checks

- check: reason, who accepted the risk
