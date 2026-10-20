# Releasing

## Readiness

The initial 0.1.x line remains early-adoption. Do not mark it stable because
metadata tests pass; native-session compatibility needs separate evidence.
GitHub workflow execution, protected reviewers, and attestation availability
cannot be validated solely from the local files.

Approved owners, repository identity, and private reporting routes are required.
See [GitHub setup](github-setup.md) and [governance](../GOVERNANCE.md).

## Prepare a reviewed version

1. Update Python, catalog, root APM, and every bundle version together.
2. Add a dated changelog entry and migration/rollback guidance.
3. Audit existing delivery before intentionally regenerating APM-owned output.
4. Run the same local/CI gates and the real APM smoke test.
5. Build only current wheel, source distribution, and fullstack-plus-IaC source ZIP.
6. Run `uv run --locked python -m scripts.check_release`; it checks exact inventory, metadata, licenses,
   source ZIP provenance, produces basename-only `build/SHA256SUMS`, and stages
   the verified flat inventory in `build/release/` for upload.
7. Run `uv run --locked python scripts/check_governance.py --publication`
   and obtain independent review.

Stale or extra build products fail the release check instead of being uploaded
through a permissive wildcard. Remove only identified old artifacts deliberately.
No command in this guide initializes version control or publishes remotely.

## Draft workflow

An operator creates the approved `v<version>` tag after the review.
The release workflow calls the shared verification workflow at the same commit.
That workflow builds and checks products; the publishing job downloads its
same-run flat artifact, verifies checksums, and waits on the `release` environment.
Uploading several source directories preserves nesting; only the staged directory
is uploaded so basename-only checksum verification remains correct.

For public repositories, it creates build-provenance attestations and a **draft
prerelease**, never an automatic stable publication. The GitHub CLI uses only
the job-scoped token, not a developer's authenticated profile.
No PyPI publishing or persistent credential is configured.

The operator checks the draft, verifies the tag/source and attestation, then
publishes intentionally. If an identically named release already exists, the
creation command fails instead of overwriting it.

## Verify artifacts

- `SHA256SUMS` detects byte corruption when obtained from a trusted source.
- It is not a signature or proof of publisher identity.
- Use GitHub CLI attestation verification against the approved repository for
  hosted build provenance; do not trust an unattested local build as hosted evidence.
- Preserve the previous source revision, locks, and selected package for rollback.
- Document corrective releases; do not replace bytes in an already published version.

Reference: [artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations),
[reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows),
and [draft creation flags](https://cli.github.com/manual/gh_release_create).
