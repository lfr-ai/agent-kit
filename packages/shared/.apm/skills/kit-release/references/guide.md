# Review what will actually be distributed

## Local candidate

Resolve one authoritative version and source revision. Build a fresh candidate
with the declared locked toolchain. Inspect wheel/source/archive contents,
licenses, package data, checksums and accidental private/generated files.
Exercise installation away from the checkout and verify only claimed targets.

For agent capabilities, archive selected source, not an accidental recursive
monorepo or empty archive. Validate provenance before regeneration can replace
the evidence. A file format check is not a native host session.

## Hosted operator gate

Check owner/contact consistency, protected required reviews, least-privilege CI,
immutable action/dependency pins, private vulnerability reporting and release
artifact provenance. These require hosted inspection and operator approval;
a committed policy file cannot enable a GitHub repository setting.
Use short-lived identity where supported. Do not publish from an untrusted PR.

## Quality gates

- Version, changelog, license and artifact inventory agree.
- Checksums describe exactly the candidate files, not stale build output.
- A clean consumer can install/use the shipped content.
- No secrets, private facts or unsupported platform claims are included.
- Signing, tagging and publication occur only through the approved operator.

## Failure and recovery

If an artifact differs from tested source, rebuild a new candidate and rerun
checks. Never overwrite a published version or silently replace checksums.
Retain the previous release and documented consumer rollback path.

Sources: [OpenSSF OSPS baseline](https://baseline.openssf.org/),
[GitHub Actions security](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions),
[artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations).
