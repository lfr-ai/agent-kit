# Evidence before completion

## Select checks by changed boundary

Start with the focused regression, then the owning formatter/linter/type/import
contracts, and finally the repository's declared completion gate. Run the final
gate after the last relevant edit. Record exact commands, environment, exit
status and unavailable prerequisites without copying sensitive logs.

Agent setup additionally needs metadata/resource containment, selection budgets,
role/tool permissions, generated drift and real install/compile checks.
Application setup needs its own behavioral, DI, migration and dependency-license
checks. One does not substitute for the other.

## Quality gates

- The original symptom is reproduced and the changed behavior is measured.
- At least the highest-risk negative and recovery cases are exercised.
- Read-only audits run before any regeneration updates ownership hashes.
- No formatter, fixer or regeneration is hidden inside a check-only gate.
- Full gate failures are separated into caused, coupled and pre-existing issues.
- Live host/cloud/model behavior is claimed only when that surface was exercised.

## Failure and recovery

If a gate fails, retain the exact failing diagnostic and investigate only its
relevant paths. Do not lower thresholds, delete assertions, accept malformed
inputs or regenerate away drift. Missing credentials or tools are explicit
limitations. A successful subprocess launch is not proof of responsive service;
check its actual health/result when starting a background process.

## Deeper references

- [Gate ordering and check-only versus fix modes](gate-ordering.md)
- [Toolchain metafiles](toolchain-metafiles.md)
- [Spell checking and link checking](spell-and-link-checking.md)
- [Secrets scanning](secrets-scanning.md)
- [Pre-commit and CI parity](precommit-ci-parity.md)
- [Evidence reporting](evidence-reporting.md)

## Sources

- [Agent Skills specification](https://agentskills.io/specification)
- pytest, [Exit codes](https://docs.pytest.org/en/stable/reference/exit-codes.html)
