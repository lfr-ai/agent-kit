---
name: kit-release
description: Use when reviewing release readiness and artifact integrity without publishing or changing remote state.
license: MIT
---

# Review a release candidate

## Procedure

1. Read the release policy, version source, supported targets and operator
   ownership. Copy the [release checklist](assets/release-checklist.md.template)
   for this release.
2. Define or confirm the public API, then choose the next version with the
   [SemVer rules](references/semver.md), including breaking changes and
   deprecations.
3. Review commit history with [Conventional Commits and commitizen](references/conventional-commits.md);
   start a missing configuration from the [commitizen template](assets/cz.toml.template)
   and use `cz bump --dry-run` as a proposal, not a decision.
4. Edit the changelog section for users and check that every claim matches
   shipped content and does not overstate runtime testing.
5. Check version and license alignment across package metadata, version files
   and distributable manifests.
6. Build into a fresh, contained output directory with the locked toolchain;
   never overwrite a consumer project.
7. Inspect artifact contents for secrets, private files, generated debris and
   missing license notices; install from the artifact outside the source tree.
8. Generate checksums for exactly the files to publish and run the declared
   release checks, recording each result and skipped prerequisite in the
   [candidate record](assets/release.md.template).
9. Prepare a signed annotated tag as described in [tagging](references/tagging.md);
   pushing it is publication and belongs to the authorized operator.
10. For hosted releases, adapt the [release workflow template](assets/release.yml.template)
    following [release workflow with attestations](references/release-workflow.md):
    per-job permissions, SHA-pinned actions, environment approval, build once,
    attest, verify checksums, publish.
11. After publication, verify attestations with `gh attestation verify` and
    document the previous supported version and rollback path.

The [release gates](references/guide.md) summarize the hosted operator checks.

## Acceptance gates

- One authoritative version; tag, manifests and changelog heading agree.
- The changelog lists every user-visible change, with breaking changes and
  migrations stated.
- The completion gate passed on the release commit; artifacts were built from
  a clean checkout and installed outside the source tree.
- Checksums and attestations describe exactly the published files.
- Tags are annotated, signed and protected; no published tag or asset was
  moved or replaced.
- Signing, tagging, pushing and publication were done only by the authorized
  operator; a local build is not reported as proof of remote protection.
