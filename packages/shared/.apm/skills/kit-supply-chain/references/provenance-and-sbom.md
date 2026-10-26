# Provenance, SBOM and automation pins

Review date: 2026-10-23.

Provenance answers "which source, workflow and inputs produced this file".
An SBOM answers "what is inside it". Both are only useful when bound to the
artifact digest and verified by the consumer.

## Automation references

| Reference | Pin | Updated by | Detailed owner |
| --- | --- | --- | --- |
| GitHub Action or reusable workflow | full 40-character commit SHA plus a version comment | Dependabot `github-actions` | `kit-ci-review` (SHA pins, zizmor, permissions) |
| Same-repository action or workflow | self-repository syntax, reviewed with the change | not needed | `kit-ci-review` |
| Container image (Dockerfile, job container, hook image) | tag plus `@sha256:` digest | Dependabot `docker` or Renovate | `kit-containers` |
| pre-commit hook repository | full commit SHA with a frozen comment | Dependabot `pre-commit` | `kit-verify-change` |
| Tool installer in CI (uv, Bun, Node) | exact version | manual or bot | `kit-ci-review` |

Run zizmor on every workflow change; its `unpinned-uses` audit enforces the
pin policy and other audits catch template injection, credential persistence
and cache poisoning.

## Decide whether an SBOM is needed

A lockfile records resolved dependencies for installation and auditing. An SBOM
provides a standardized component inventory for release consumers and downstream
systems. Neither one alone detects vulnerabilities or proves that code is safe.

Keep the lockfile and existing audits as the development baseline. Adopt SBOM
generation when a consumer, compliance rule, or release-inventory system needs
it; otherwise record the deferral in the supply-chain policy. Do not add an SBOM
generator or Trivy gate merely because a lockfile exists. Build provenance is a
separate release control and does not require SBOM generation.

For a published library, the lock describes the tested dependency set, not every
consumer's installation and not packages bundled inside its wheel. Label a
lock-derived SBOM accordingly. For deployed applications and images, capture the
target platform and resolved or installed runtime components. Keep development
and build tooling in a separate inventory when required.

## SBOM formats and generators

| Format | Strength | Typical generator |
| --- | --- | --- |
| CycloneDX (JSON) | security tooling, vulnerability exchange, wide scanner support | `uv export --format cyclonedx1.5` (uv preview feature `sbom-export`), `cyclonedx-py environment` for an installed environment, Syft |
| SPDX (JSON) | license compliance, ISO/IEC 5962 standard | Syft, `docker buildx build --sbom=true` for images |

When adopted:

- Generate the SBOM from the lock or the built artifact in the same job that
  builds the artifact, never from a developer machine.
- State whether the inventory describes a resolved dependency set or the built
  artifact's installed contents. Exclude development groups from a runtime SBOM
  (`--no-default-groups` for uv); do not describe a library's tested dependency
  versions as dependencies bundled in its wheel.
- Attest the SBOM to the artifact digest (`actions/attest` with `sbom-path`)
  so it cannot be swapped for another build's SBOM.
- Keep the SBOM with the release, and store image SBOMs with the image digest.

## Build provenance and signatures

| Mechanism | What it proves | Consumer check |
| --- | --- | --- |
| SLSA Build L1 | provenance exists and describes the build | provenance is present |
| SLSA Build L2 | provenance is signed by a hosted build platform | signature verifies against the platform identity |
| SLSA Build L3 | the build platform isolates runs and protects signing material | identity is a hardened builder |
| Sigstore keyless signing | the artifact was signed by an OIDC identity at a time recorded in a transparency log | certificate identity and issuer match the expected workflow |
| GitHub artifact attestations | a GitHub Actions run of a given repository and workflow produced this digest (SLSA provenance, signed through Sigstore) | `gh attestation verify <file> --repo <owner>/<repo>`, optionally with `--signer-workflow` |
| PyPI trusted publishing | the upload came from a configured CI workflow without a long-lived token | project settings name the workflow and environment |
| PyPI attestations (PEP 740) | each distribution is bound to the publishing identity; the official publish action produces them by default with trusted publishing | attestations shown on the file page and in the index API |
| npm provenance | `npm publish --provenance` links the package to its source and build | `npm audit signatures` |

GitHub artifact attestations need `id-token: write`, `attestations: write` and
`artifact-metadata: write` on the attesting job, and are available for public
repositories and for private ones on plans that support them. Use the
[SBOM workflow template](../assets/sbom.yml.template); publishing and release
gates belong to `kit-release`.

## Consuming provenance

- Prefer dependencies that publish attestations or signed releases; record it
  in the adoption review.
- Where a dependency publishes provenance, verify it in CI before use, for
  example `gh attestation verify` for a downloaded release asset.
- Provenance proves where something was built, not that the source is safe.

## Failure modes

- **Attest then rebuild.** The attested digest no longer matches what ships.
- **Broad attestation permissions.** `id-token: write` granted to every job
  lets unrelated steps mint signing identities; grant it to the attesting job
  only.
- **SBOM scope drift.** Manifest ranges do not identify installed versions, and a
  library lock does not identify every consumer's environment. State the inventory
  scope rather than claiming those components were bundled in the artifact.
- **Unverified provenance.** Generating attestations without any consumer
  check provides no protection.

## Primary sources

Reviewed 2026-10-23.

- SLSA, [Security levels v1.1](https://slsa.dev/spec/v1.1/levels)
- Sigstore, [Documentation](https://docs.sigstore.dev/)
- GitHub, [Artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations)
- GitHub, [actions/attest-build-provenance (wrapper of actions/attest)](https://github.com/actions/attest-build-provenance)
- GitHub, [Secure use of GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use)
- PyPI, [Trusted publishers](https://docs.pypi.org/trusted-publishers/) and [Attestations](https://docs.pypi.org/attestations/)
- Python, [PEP 740: index support for digital attestations](https://peps.python.org/pep-0740/)
- uv, [Exporting a lockfile: CycloneDX](https://docs.astral.sh/uv/concepts/projects/export/)
- CycloneDX, [Specification overview](https://cyclonedx.org/specification/overview/) and [cyclonedx-python](https://github.com/CycloneDX/cyclonedx-python)
- SPDX, [Specifications](https://spdx.dev/use/specifications/)
- zizmor, [Audit rules](https://docs.zizmor.sh/audits/)
- OpenSSF, [Scorecard checks](https://github.com/ossf/scorecard/blob/main/docs/checks.md)
