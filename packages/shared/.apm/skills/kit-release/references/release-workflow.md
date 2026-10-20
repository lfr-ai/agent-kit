# GitHub release workflow with build attestations

The [release workflow template](../assets/release.yml.template) builds once
from a pushed version tag, attests the exact files it built, and publishes
those same files as a GitHub release after an environment approval. This page
explains each choice so it can be adapted without weakening it.

## Shape

```text
push tag v1.4.0
  -> build job (contents: read, id-token: write, attestations: write)
       checkout tag -> verify tag == package version -> completion gate
       -> build dist/ -> SHA256SUMS -> attest dist files -> upload artifact
  -> publish job (environment: release, contents: write)
       download artifact -> verify checksums -> extract changelog section
       -> gh release create --verify-tag
```

## Security choices

| Choice | Why |
| --- | --- |
| `permissions: {}` at the top, granted per job | each job gets only what it needs; the default token is read-only or none |
| `id-token: write` and `attestations: write` only in the build job | the OIDC token and attestation API are needed only where the attestation is created |
| `contents: write` only in the publish job | creating a release needs it; building does not |
| `environment: release` with required reviewers | a person approves publication; environment secrets, if any, are only exposed after approval |
| actions pinned to full commit SHAs with a version comment | a tag of a third-party action can be moved; a SHA cannot |
| `persist-credentials: false` on checkout | the token is not left in `.git/config` for later steps |
| untrusted values passed through `env`, never interpolated into `run` | prevents script injection from tag names or other event data |
| triggered by tag push only | no pull request from a fork can reach the publish job |
| build once, publish the same files | what is attested and covered by checksums is exactly what users download |

Keep Dependabot (or another updater) configured for GitHub Actions so pinned
SHAs are proposed for update with their new version comments.

## Build provenance attestations

`actions/attest` creates a signed in-toto attestation that binds each file's
digest to the workflow, repository, commit and run that produced it, using a
short-lived certificate issued for the workflow's OIDC identity (Sigstore).
Public repositories record it in the public transparency log; private
repositories use GitHub's private instance.

Consumers verify a downloaded file with the GitHub CLI:

```text
gh attestation verify dist/shop-1.4.0-py3-none-any.whl --repo example-org/shop
```

Verification can additionally pin the signer workflow
(`--signer-workflow`) and require the source ref, so an attestation from a
different workflow in the same repository is rejected. Document the exact
verification command in the release notes or security policy.

For container images use `subject-name` and `subject-digest` (the pushed
digest, never a tag) and `push-to-registry: true`. For an SBOM, generate it in
the build job and attest it with `sbom-path`.

An attestation proves where and how a file was built. It does not prove the
source was reviewed or free of vulnerabilities; those come from branch rules,
code review and scanning.

## Adapting the template

1. Replace each `REVIEWED_COMMIT_SHA` with the full SHA of the release named in
   the comment, after reviewing that release.
2. Replace the version check, completion gate and build commands with the
   project's own. Keep the tag/version comparison: it catches tagging the wrong
   commit.
3. Keep `--verify-tag` so the release fails if the tag does not exist remotely
   instead of creating a new tag from the default branch.
4. Create the `release` environment with required reviewers and, ideally, a
   deployment branch/tag rule limited to `v*` tags.
5. If packages are published to a registry, add a separate job that depends on
   `build`, uses the same artifact, and authenticates with the registry's
   trusted publishing (OIDC) instead of a long-lived token.
6. Protect `v*` tags with a ruleset; see [tagging](tagging.md).

## Failure and recovery

- **Tag/version mismatch**: delete nothing; fix the version, release a new tag.
  If the bad tag was pushed but not released, the operator decides whether
  removing it is safe (nobody fetched it) or whether to skip that version.
- **Gate fails on the tag**: the release commit is broken; fix forward with a
  new version.
- **Attestation step fails**: do not publish unattested files. Check the job
  permissions and that the repository plan supports attestations.
- **Publish job fails after the release was partially created**: inspect the
  draft or partial release; delete only that incomplete release object, never
  the tag, and re-run the job.
- **Wrong files published**: never replace assets of a published release.
  Mark the release as superseded in its notes, yank the registry version if
  applicable, and publish a new version.

## Sources

- [GitHub: using artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
- [GitHub: artifact attestations concepts](https://docs.github.com/en/actions/concepts/security/artifact-attestations)
- [actions/attest](https://github.com/actions/attest)
- [GitHub CLI: gh attestation verify](https://cli.github.com/manual/gh_attestation_verify)
- [GitHub CLI: gh release create](https://cli.github.com/manual/gh_release_create)
- [GitHub Actions: secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)
- [GitHub: managing environments for deployment](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
- [GitHub: workflow syntax, filter patterns](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#filter-pattern-cheat-sheet)
- [PyPI: trusted publishers](https://docs.pypi.org/trusted-publishers/)
