# Incident response for a compromised dependency

Review date: 2026-10-23.

Use this when a package, action, image or maintainer account the project
depends on is reported malicious or compromised, or when a locked artifact no
longer matches its recorded hash. Speed matters, but every destructive step
(revoking credentials, yanking releases, rewriting history) is an operator
action with an owner.

## Triage questions

| Question | How to answer | Why it matters |
| --- | --- | --- |
| Which versions are affected? | advisory, OSV entry (`MAL-` identifiers for malicious packages), maintainer statement | decides whether the lock is exposed |
| Is an affected version in any lock, image or cache? | search every lockfile and SBOM; `uv tree --package <name>`; `npm ls <name>` | scope of exposure |
| Was it installed, and where? | CI logs, cache keys, developer machines, built images and their SBOMs | where code may have run |
| What could install-time or import-time code reach? | job permissions, secrets in the environment, tokens on disk, network egress | which credentials to rotate |
| Did anything we published include it? | release SBOMs and attestations | whether consumers must be told |

## Procedure

1. **Freeze.** Pause dependency update merges and releases that touch the
   affected ecosystem. Do not run installs or builds that could pull the bad
   version again, including cache restores.
2. **Scope.** Answer the triage table. Use SBOMs and lockfiles from each
   release, not only the current branch.
3. **Contain.** Pin to a known-good version or remove the dependency; regenerate the lock
   with `uv lock --upgrade-package <name>` (or the ecosystem equivalent) and
   confirm with the [lock freshness checker](../assets/check_lock_freshness.py).
   Add an explicit exclusion where the tool supports one so a resolver cannot
   pick the bad version.
4. **Purge.** Invalidate CI caches, rebuild images from clean bases, and
   delete artifacts produced while the bad version was present.
5. **Rotate.** Ask the operator to revoke and reissue every credential the
   code could reach: CI secrets, registry and index tokens, cloud keys, SSH
   keys and personal tokens on affected machines. Prefer OIDC and trusted
   publishing afterwards so fewer long-lived secrets exist.
6. **Rebuild and verify.** Rebuild from the corrected lock, audit before
   install, regenerate the SBOM and provenance, and run the full gate.
7. **Notify.** If a published artifact included the bad version, the owner
   publishes an advisory, yanks or deprecates affected releases, and tells
   consumers which version is clean. Report malicious packages to the index
   (PyPI and npm both accept reports) and to the OSV malicious-packages
   repository.
8. **Learn.** Record the timeline, the controls that worked, and the control
   that would have stopped it earlier (cooldown, hash pin, review rule,
   narrower token). Update the supply-chain policy.

## Evidence to keep

- Lockfiles, SBOMs and attestations of each affected release.
- CI run identifiers and logs showing install times.
- The list of rotated credentials with timestamps (identifiers only, never
  values).

## Anti-patterns

- Upgrading past the bad version without checking whether it already ran.
- Rotating only the credential named in the advisory.
- Deleting logs or caches before scope is understood.
- Announcing the incident is closed before rebuilt artifacts are verified.

## Primary sources

Reviewed 2026-10-23.

- OpenSSF, [Malicious packages repository](https://github.com/ossf/malicious-packages)
- Google, [OSV-Scanner](https://google.github.io/osv-scanner/)
- PyPI, [Yanking releases](https://docs.pypi.org/project-management/yanking/)
- GitHub, [Secure use of GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use)
- PyPI, [Trusted publishers](https://docs.pypi.org/trusted-publishers/)
- OpenSSF, [Guides](https://openssf.org/resources/guides/)
