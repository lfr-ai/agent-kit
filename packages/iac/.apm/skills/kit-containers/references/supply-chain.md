# Image supply chain: lint, SBOM, scan, attest

## Lint the Dockerfile

- Run Hadolint on every Dockerfile change for Dockerfile best practices and
  ShellCheck diagnostics in `RUN` scripts. Review digest pins and runtime
  hardening separately; lint does not prove every container requirement.
- Fail on warnings; record inline suppressions
  (`# hadolint ignore=DL3008`) with a reason on the line above.
- Hadolint checks the build recipe, not the installed OS and library packages.
  A lint-clean Dockerfile can still produce an image with known vulnerabilities.
  Retain repository secret scanning and zizmor for their separate targets.

## Software bill of materials

- Adopt an image SBOM when a consumer, compliance rule, or release-inventory
  system needs it. `kit-supply-chain` owns this decision and the lockfile/SBOM
  distinction; do not install another generator without a requirement.
- When adopted, generate the image SBOM with BuildKit (`--sbom=true`).
  Generate build provenance independently (`--provenance=mode=max`); exporter
  support determines where attestations survive. A local Docker build is not
  evidence of publication.
- Inspect with `docker buildx imagetools inspect <image> --format
  '{{ json .SBOM }}'` or `docker scout sbom <image>`.
- Bind the SBOM to the image digest, not a mutable tag. `kit-supply-chain`
  owns SBOM distribution and its attested SBOM workflow; do not duplicate it.
- Trivy can produce SPDX or CycloneDX, but this starter produces a
  vulnerability JSON report, not a distributed or attested SBOM. CycloneDX
  generation alone does not imply vulnerability scanning.

## Vulnerability scanning

- For shipped images, use the existing image vulnerability scanner or adopt
  Trivy; do not add a second scanner for the same target without a coverage reason.
  Scan the built image, not only its Dockerfile. The opt-in
  [Trivy runner](../assets/templates/trivy_image_scan.py.template) scans only
  a local Docker image ID (`sha256:` plus 64 lowercase hex characters);
  tags and registry references are rejected. This is a single-platform image
  configuration digest, **not** the registry manifest/index digest. The release
  owner must bind the exported/published digest and scan each target platform.
- Copy the runner to `trivy_image_scan.py`. On a trusted, disposable worker
  with Python 3.13+, a working Docker daemon and an already built image:

  ```sh
  python trivy_image_scan.py --scanner /opt/reviewed/trivy \
    --scanner-version REVIEWED_EXACT_VERSION \
    --scanner-sha256 REVIEWED_BINARY_SHA256 \
    --image-id sha256:REPLACE_WITH_64_LOWERCASE_HEX \
    --evidence ./trivy-evidence
  ```

- Replace all placeholders after review; the runner rejects them. Provision
  the scanner through the consumer's approved mechanism. It verifies the
  binary SHA-256 **before execution** and compares actual version JSON to the
  reviewed version. Review these flags against that release's CLI; this
  resource neither selects a floating release nor downloads/installs a tool.
- The command explicitly selects vulnerability scanning of OS and library
  packages, precise detection, HIGH/CRITICAL severity and fixed findings only
  (`--ignore-unfixed --exit-code 1`); a defensive JSON check also rejects
  blocking findings accompanying an unexpected zero exit. Vendor severity/fix
  information determines the gate; LOW/MEDIUM/UNKNOWN and unfixed findings are
  not a clean bill of health. EOL operating systems fail with code 2. Consumers must separately
  inventory excluded findings and assign unfixable ones an owner/review date.
- The runner does not enable Trivy secret or configuration scanning. Reuse the
  repository's secret scanner and Hadolint instead of duplicating them; image
  vulnerability scanning does not replace zizmor's workflow analysis.
- Suppressions are **disallowed in this starter**: isolated working directory,
  home, cache and empty config; inherited `TRIVY_*` settings are removed;
  ignore files, Rego policies, ignored statuses and VEX are explicitly disabled.
  No arbitrary scanner arguments are accepted. A consumer exception mechanism
  requires a separate policy review with owner, reason and expiry.
- Database sources are explicitly `ghcr.io/aquasecurity/trivy-db:2` and
  `ghcr.io/aquasecurity/trivy-java-db:1`, with updates enabled and no fallback
  mirror. These are mutable database schema tags, not immutable database pins.
  Each run uses a fresh cache. Network access to those public databases is
  required; `--offline-scan` disables dependency-identification API requests,
  **not** database downloads. This can reduce dependency identification coverage.
  Use platform-managed network/proxy credentials, never source credentials.
- Evidence is a **new**, operator-chosen local directory: image/binary identity,
  exact command/policy, actual version JSON before and after scanning (including
  vulnerability DB schema, updated/next-update/download timestamps and Java DB
  metadata when used), filtered scan JSON and stderr. No synthetic DB evidence
  is substituted. Missing DB evidence or invalid/mismatched success reports fail
  closed. Scanner, database and evidence errors remain nonzero, not clean scans.
- Reports/logs may reveal package names, image metadata or paths. There is no
  upload action, artifact glob, registry login, push or deployment. The operator
  owns access control, a finite retention period, size limits and any explicitly
  approved upload of **only** this directory; do not upload the workspace,
  Docker credentials or temporary database cache. The cache is deleted on exit;
  metadata is not a database blob digest or a complete reproducibility archive.
- Run with no competing image/cache mutation and a trusted reviewed binary;
  file hashing does not authenticate its publisher. The runner does not verify
  scanner signatures, coverage of every package, runtime safety or exploitability.
  It assumes the consumer has reviewed Docker access and database availability.
- Schedule repeat scans/rebuilds through the consumer's CI owner because new
  CVEs appear for unchanged images; nothing here installs a scheduled job.
- Rebuild regularly to pick up base image patches even without code changes.

### Offline validation and rollback

Resource/syntax guards and stubbed-process tests validate the shipped command,
pin checks and failure propagation; they are **not** a real image scan. Before
adoption, the operator must run the reviewed scanner against the actual image
and retain the evidence, including a known-finding/failure exercise.

Rollback: remove the opt-in invocation and copied runner, revert the linked
resource/prose changes, and remove local evidence under the retention policy.
No registry, deployment, infrastructure state or SBOM distribution is changed.
Already uploaded evidence cannot be recalled by reverting source.

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
- [ ] Shipped image has provenance; SBOM generated and attested when required.
- [ ] Image scan gate on fixable HIGH and CRITICAL findings.
- [ ] Deployments reference image digests.
- [ ] Scheduled rebuild and repeat scan exist.

Template: [Hadolint configuration](../assets/templates/hadolint.yaml.template).

## Sources

Trivy primary documentation reviewed 2026-10-24 from the official upstream
repository (the rendered site returned HTTP 403). Recheck release-sensitive
flags when choosing the scanner pin:

- <https://github.com/hadolint/hadolint#configure>
- <https://docs.docker.com/build/metadata/attestations/sbom/>
- <https://docs.docker.com/build/metadata/attestations/slsa-provenance/>
- <https://docs.docker.com/scout/>
- <https://raw.githubusercontent.com/aquasecurity/trivy/main/docs/guide/target/container_image.md>
- <https://raw.githubusercontent.com/aquasecurity/trivy/main/docs/guide/scanner/vulnerability.md>
- <https://raw.githubusercontent.com/aquasecurity/trivy/main/docs/guide/configuration/others.md>
- <https://raw.githubusercontent.com/aquasecurity/trivy/main/docs/guide/configuration/filtering.md>
- <https://raw.githubusercontent.com/aquasecurity/trivy/main/docs/guide/configuration/db.md>
- <https://raw.githubusercontent.com/aquasecurity/trivy/main/docs/guide/supply-chain/sbom.md>
- <https://raw.githubusercontent.com/aquasecurity/trivy/main/docs/guide/references/configuration/cli/trivy_image.md>
- <https://raw.githubusercontent.com/aquasecurity/trivy/main/pkg/version/version.go>
- <https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds>
