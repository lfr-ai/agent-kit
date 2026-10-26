# Supply-chain guide

Review date: 2026-10-23. Tool flags and defaults change between releases;
confirm version-sensitive options against the primary sources before adopting.

## What this skill owns

The decision to admit, constrain, audit, update and remove third-party code,
and the evidence that ties a shipped artifact to its inputs. Mechanics that
another skill already owns are linked by name, not repeated here.

| Concern | Owner | What to use there |
| --- | --- | --- |
| Admission, constraints, audit order, cooldown policy, SBOM, incidents | `kit-supply-chain` | this skill |
| Floating versions in hooks, workflows, images, package runners | `kit-verify-change` | `check_pins.py` and its version-pinning reference |
| Installed license evaluation | `kit-agent-runtime` | `license_guard.py` and the license-guard reference |
| Update bot choice and configuration | `kit-repository-setup` | Dependabot and Renovate templates, dependency-updates reference |
| Workflow SHA pins, zizmor, dependency review job, audit job | `kit-ci-review` | supply-chain reference, dependency-audit and zizmor templates |
| Image digests, image SBOM and image provenance | `kit-containers` | supply-chain reference |
| Publishing, trusted publishing, release attestations | `kit-release` | release workflow reference and template |
| Dependency use in application code | `kit-secure-code` | OWASP mapping (A03 Software Supply Chain Failures) |
| Upgrade batching and abandoned-package replacement | `kit-modernize` | dependency-upgrades reference |

## Decision table

| Situation | Action | Reference |
| --- | --- | --- |
| Someone proposes a new package | Adoption review before the manifest changes | [dependency selection](dependency-selection.md) |
| A package name came from an assistant, a blog or a typo-prone memory | Verify the exact name, owner and index first | [dependency selection](dependency-selection.md) |
| Application or internal tool | Exact versions in the lock with hashes | [locking and auditing](locking-and-auditing.md) |
| Library published for others | Bounded ranges in metadata; lock the tested build | [locking and auditing](locking-and-auditing.md) |
| Manifest or lockfile changed | Lock freshness check, audit, then install | [locking and auditing](locking-and-auditing.md) |
| Update bot proposes a version | Cooldown elapsed, audit and gates pass, then merge | [locking and auditing](locking-and-auditing.md) |
| Artifact is published | Build provenance bound to the released digest | [provenance and SBOM](provenance-and-sbom.md) |
| Consumer, compliance, or inventory system requires an SBOM | Generate and attest an inventory for the same released digest | [provenance and SBOM](provenance-and-sbom.md) |
| Advisory for a locked version | Upgrade or time-boxed exception with reachability notes | [locking and auditing](locking-and-auditing.md) |
| Package reported malicious or an account compromised | Incident procedure | [incident response](incident-response.md) |
| Declared package no longer imported | Confirm, remove, regenerate the lock | [dependency selection](dependency-selection.md) |

## Choose tools by risk and target

Keep one primary tool per row; reuse it locally and in CI. Add a second tool
only for a documented coverage or enforcement-boundary difference, not another
report of the same findings.

| Need | Primary choice | Boundary |
| --- | --- | --- |
| Committed secrets | detect-secrets or Gitleaks | Reuse the chosen scanner in CI; history and hosting push protection cover other boundaries |
| Workflow correctness and security | actionlint plus zizmor | Valid syntax and safe workflow behavior are different properties |
| Locked dependency vulnerabilities | Existing ecosystem audit, such as pip-audit and Bun audit | Do not add Trivy language-package scanning over the same locks by default |
| Dockerfile quality | Hadolint | Lints the recipe, not installed packages |
| Built-image vulnerabilities | Existing image scanner or opt-in Trivy with `--scanners=vuln` | Inspect OS and library packages in the actual image; `kit-containers` owns the runner |
| Infrastructure misconfiguration | Trivy configuration scanning or Checkov | Choose one; neither replaces workflow security or the repository secret scanner |
| Release component inventory | SBOM export when required | Not a vulnerability scan; prefer the existing package manager or image builder |

## Failure modes

- **Approval by popularity.** Stars and downloads are cheap to inflate and say
  nothing about who can publish the next release.
- **Install before audit.** Installing a changed lock runs build backends and
  install scripts before the advisory check has had a chance to fail.
- **Lock drift.** The manifest changes without a new lock, or the lock is
  regenerated with unrelated upgrades in the same change.
- **Mutable references.** Tags, branches, `latest` images and URLs without hashes
  can change after review.
- **Cooldown everywhere.** A global resolver cut-off also blocks the security
  fix published this week; delay version updates only.
- **SBOM without binding.** An SBOM that is not attested to the artifact
  digest can describe a different build.
- **Silent exceptions.** An ignored advisory or license without an owner and
  an expiry date becomes permanent.

## Anti-patterns

- Adding a dependency for a few lines that the standard library covers.
- `pip install`, `npx`, `uvx` or `bun add` run ad hoc instead of a reviewed
  manifest and lock change.
- An extra index added with `--extra-index-url` next to the public index.
- Disabling hash checking, lockfile checks or audit failures to make CI pass.
- Two update bots managing the same manifest.
- Multiple scanners for the same risk and target without a coverage reason.

## Verification

1. `python check_lock_freshness.py --project pyproject.toml --lock uv.lock`
   exits 0.
2. `uv lock --check` (or the ecosystem's frozen-lockfile install) agrees.
3. The vulnerability audit ran against the lock before installation and its
   output is attached to the change.
4. The license guard passes on the installed environment.
5. For a release, `gh attestation verify <file> --repo <owner>/<repo>`
   succeeds for each published file.

## Primary sources

Reviewed 2026-10-23.

- OpenSSF, [Concise guide for evaluating open source software](https://best.openssf.org/Concise-Guide-for-Evaluating-Open-Source-Software)
- OpenSSF, [Scorecard checks](https://github.com/ossf/scorecard/blob/main/docs/checks.md)
- SLSA, [Security levels v1.1](https://slsa.dev/spec/v1.1/levels)
- Sigstore, [Documentation](https://docs.sigstore.dev/)
- PyPA, [Secure installs with pip](https://pip.pypa.io/en/stable/topics/secure-installs/)
- uv, [Locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- GitHub, [Artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations)
- GitHub, [About dependency review](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/about-dependency-review)
