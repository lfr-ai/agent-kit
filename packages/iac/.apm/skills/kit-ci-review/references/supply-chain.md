# Supply chain: pinning, updates, caches, and attestations

## Pin actions to full commit SHAs

A tag such as `v4` or a branch such as `main` is mutable: the action owner, or
anyone who compromises the owner's account, can move it. A full 40-character
commit SHA is the only immutable reference for a repository action.

- Pin every third-party action and reusable workflow as
  `owner/repo@<40-hex-sha> # vX.Y.Z`. The trailing comment keeps the human
  version visible and lets Dependabot update both together.
- Short SHAs are not immutable references; always use the full SHA.
- Verify the SHA belongs to the action's own repository, not a fork network
  object, by resolving it from the upstream tag before pinning.
- Pin container actions (`docker://`) and job `container:` images by digest
  (`image@sha256:...`).
- Organization policy can require SHA pinning for all actions and restrict
  which actions are allowed; enable it where available and record exceptions.
- Actions in the same repository (`./path`) are reviewed with the change and
  need no pin. Actions owned by your organization may be exempted by policy;
  pass `--trusted-owner` to the checker to encode that policy explicitly.

## Keep pins current with Dependabot

Pinned SHAs only stay safe if they are updated. Configure the
`github-actions` ecosystem so Dependabot proposes SHA bumps with the new
version comment. Group minor and patch updates to reduce noise, keep majors
separate, and apply a cooldown so brand-new releases age before adoption.
See [the Dependabot template](../assets/templates/dependabot.yml.template).

## Cache and artifact integrity

- Caches are scoped by branch: a pull request can read caches from its base
  branch but writes only to its own ref. Still, never restore a cache into a
  privileged job when the cache key could have been written by an untrusted run.
- Include lockfile hashes in cache keys so a dependency change cannot reuse a
  stale or tampered cache.
- Do not cache credentials, `.npmrc` files with tokens, or cloud login state.
- Set short `retention-days` on artifacts and never upload workspace roots that
  may contain `.git/config` credentials written by checkout. Use
  `persist-credentials: false` on checkout when later steps do not push.

## Artifact attestations

Build provenance attestations bind an artifact digest to the workflow, commit,
and runner that produced it, signed with a short-lived Sigstore certificate.

- The attesting job needs `id-token: write` and `attestations: write`
  (plus `packages: write` when pushing an image attestation to a registry).
- Attest the exact digest that is published; attesting a file and then
  rebuilding it breaks the chain.
- Consumers verify with `gh attestation verify <artifact> --repo <owner>/<repo>`
  (or `--owner`), optionally constraining the signer workflow.
- Attestations prove where and how an artifact was built. They do not prove
  the source was safe; combine them with review and dependency scanning.
- For SBOMs, generate the document during the build and attest it with the
  SBOM attestation action so the SBOM is bound to the same digest.

## Dependency review

- Run dependency review on pull requests to block newly introduced packages
  with known vulnerabilities or disallowed licenses.
- Enable secret scanning and push protection at the repository level.

## Review checklist

- [ ] Every external `uses:` is pinned to a full SHA with a version comment.
- [ ] Dependabot covers the `github-actions` ecosystem.
- [ ] Cache keys include lockfile hashes; privileged jobs do not restore
      caches writable by untrusted runs.
- [ ] Checkout uses `persist-credentials: false` unless a later step pushes.
- [ ] Published artifacts carry provenance attestations for their digests.

## Sources

- <https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions>
- <https://docs.github.com/en/code-security/dependabot/working-with-dependabot/keeping-your-actions-up-to-date-with-dependabot>
- <https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference>
- <https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds>
- <https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/caching-dependencies-to-speed-up-workflows>
