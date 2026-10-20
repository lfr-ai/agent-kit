---
name: kit-apm-audit
description: Use when verifying owned APM output, dependency integrity, drift, or policy changes.
license: MIT
---

# Audit before regeneration

1. Establish source revision, CLI version, selected targets, and the deployment owner.
2. Verify manifest/provenance hashes before installation can refresh them.
3. Audit with an explicit policy path; do not assume the filename activates policy.
4. Inspect unsupported fields, missing capabilities, and unowned files separately.
5. Reproduce frozen deployment in a disposable workspace.
6. Exercise a deliberately changed fixture and confirm the audit rejects it.
7. Report exact commands, exit codes, tested surfaces, and remaining gaps.

An integrity check is not a sandbox, freshness check, or behavioral certification.
Do not use force or strip options to hide a failing audit.

See the [gate contract](references/gates.md).
For a consumer that already declares the pinned APM environment, use the
[check-only workflow steps](assets/apm-audit-steps.yml.template).
