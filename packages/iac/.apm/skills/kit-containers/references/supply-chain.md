# Image supply chain: lint, SBOM, scan, attest

## Lint the Dockerfile

- Run Hadolint on every Dockerfile change. It catches unpinned bases,
  `latest` tags, root final users, shell-form entrypoints, missing
  `pipefail`, and unpinned package installs, and runs ShellCheck on `RUN`
  scripts.
- Fail on warnings; record inline suppressions
  (`# hadolint ignore=DL3008`) with a reason on the line above.

## Software bill of materials

- Generate an SBOM at build time with BuildKit:
  `docker buildx build --sbom=true --provenance=mode=max ...` attaches an
  SPDX SBOM and SLSA provenance attestation to the pushed image.
- Inspect with `docker buildx imagetools inspect <image> --format
  '{{ json .SBOM }}'` or `docker scout sbom <image>`.
- Keep the SBOM with the image digest, not with a mutable tag.

## Vulnerability scanning

- Scan the built image (not only the Dockerfile) before push and on a schedule
  after push, because new CVEs appear for unchanged images.
- Fail the build on fixable HIGH and CRITICAL findings; track unfixable ones
  with an owner and review date.
- Scanners: `docker scout cves`, Trivy (`trivy image`), Grype. Use one
  consistently and pin its version and database source in CI.
- Rebuild regularly to pick up base image patches even without code changes.

## Provenance and signing

- Push by digest and deploy by digest. Tags are for humans.
- Attach build provenance (BuildKit `--provenance=mode=max`, or GitHub
  artifact attestations for the pushed digest) so consumers can verify which
  workflow and commit produced the image.
- Verify before deploy (for example `gh attestation verify
  oci://<registry>/<image>@<digest> --owner <org>`) and enforce verification
  in the cluster admission policy where available.

## Registry hygiene

- Only push from protected CI jobs; developers never push release tags.
- Enable immutable tags where the registry supports it.
- Restrict pull access to the identities that deploy.

## Review checklist

- [ ] Hadolint passes with reasoned suppressions only.
- [ ] Image built with SBOM and provenance attestations.
- [ ] Image scan gate on fixable HIGH and CRITICAL findings.
- [ ] Deployments reference image digests.
- [ ] Scheduled rebuild and repeat scan exist.

Template: [Hadolint configuration](../assets/templates/hadolint.yaml.template).

## Sources

- <https://github.com/hadolint/hadolint#configure>
- <https://docs.docker.com/build/metadata/attestations/sbom/>
- <https://docs.docker.com/build/metadata/attestations/slsa-provenance/>
- <https://docs.docker.com/scout/>
- <https://trivy.dev/docs/latest/guide/target/container_image/>
- <https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds>
