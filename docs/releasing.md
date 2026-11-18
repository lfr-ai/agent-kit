# Releasing

## Readiness

The initial 0.1.x line remains early-adoption. Do not mark it stable because
metadata tests pass; native-session compatibility needs separate evidence.
GitHub workflow execution, protected reviewers, and attestation availability
cannot be validated solely from the local files.

Approved owners, repository identity, and private reporting routes are required.
See [GitHub setup](github-setup.md) and [governance](../GOVERNANCE.md).

## First publication: no Azure account required

This is a GitHub source and artifact release, not an infrastructure deployment.
The release workflow never runs Azure login, provisions resources, or reads the
operator's current Azure subscription. Leave application deployment environments
and their Azure credentials out of release setup. GitHub's OIDC permission here
is used for coverage and artifact attestations, not Azure authentication.

For the first release:

1. Review the complete staged and unstaged changes on a release branch.
   Check publication contacts, synthetic fixtures, licenses and Git history
   for private data; checking only today's worktree does not clear history.
2. Resolve the [Copier license decision](dependency-security.md#copier-development-tool).
   Do not skip its gate or label a failed release build as approved.
3. Keep the existing `0.1.0` version if that is the intended first version.
   `version:prepare` calculates a *new* version; it is not required merely to
   publish an already prepared version. Review every versioned manifest and
   the dated changelog before committing.
4. Run `task verify`, `task apm:smoke`, `task release:build`, and the publication
   governance check below. Resolve failures and obtain independent review.
5. Configure the GitHub `release` environment and applicable branch/tag
   protections. The current draft-publishing job is public-repository-only;
   private repositories need a reviewed workflow and plan-specific protections.
6. The operator merges the reviewed source and creates/pushes the approved
   version tag. This triggers the existing release workflow; it does not deploy
   applications. Wait for verification and the protected environment approval.
7. Review the resulting draft prerelease, source commit, checksums and
   attestations. Run the `gh attestation verify` commands in "Verify artifacts"
   on the downloaded draft assets; only then run `task release:publish TAG=v0.1.0` as the operator.
8. Test generation and installation from the remotely available revision in a
   fresh directory. Local-source substitutions do not prove this works.

A Git tag/commit that exists remotely is what Git-based dependencies resolve.
A published GitHub Release page is not technically required to fetch that
commit, and publishing a page does not repair an unavailable Git reference.
The starter's executable workflow, runtime and Terraform references must use
the reviewed full commit containing those files. Do not select the current
`HEAD` while the intended implementation exists only as uncommitted changes.
Keep the APM profile release coordinates and their resolved lock consistent too.
PyPI publication is separate and is not configured by this workflow.

## Prepare a reviewed version

Use the Task entry points rather than reconstructing flags:

| Action | Command | Writes |
| --- | --- | --- |
| Preview next version and commit-derived notes | `task version:preview` | Nothing |
| Prepare versions from Conventional Commits | `task version:prepare` | Version metadata and `uv.lock`, after confirmation |
| Build and verify exact local release products | `task release:build` | Two wheels, two sdists, source ZIP, checksums and staging |
| Publish a reviewed workflow-created draft | `task release:publish TAG=v0.1.1` | Remote release visibility, after confirmation |

`version:prepare` requires clean tracked changes. Run it on an operator-created
release branch after reviewing `version:preview`. Commitizen's
`--version-files-only` updates the PEP 621 version and configured APM metadata
alongside the runtime workspace version and starter's toolkit reference, without
committing or creating a tag. The curated changelog remains manual:
review the generated preview, keep an Unreleased section, and add the dated
release entry before committing.

The artifact checker reads `packages/runtime/pyproject.toml` separately and
accepts a runtime version different from the toolkit/APM version. This is
independent **metadata validation**, not an independent version-preparation
workflow. The current `.cz.toml` configuration coordinates toolkit/APM versions,
the runtime workspace version, its root development-dependency pin, and the
starter reference; `version:prepare` then updates `uv.lock`.
Separating that operator workflow requires a separately reviewed change.
Do not use `version:prepare` as an independent runtime bump command.

Keep the changelog focused on reader decisions:

- Group related user-visible changes; omit commit lists and test-run narration.
- Lead with the effect, then any required migration or setup step.
- Use only applicable Keep a Changelog categories; put vulnerability fixes in
  Security and distinguish available configuration from activated integrations.
- Preserve dated release history. Use generated notes as input, not a replacement
  for the curated entries.

The operator reviews, commits and merges that preparation, then creates/pushes
the approved version tag. The tag workflow below builds the draft from that
commit. `release:publish` does not create tags, upload replacement artifacts,
change prerelease status or bypass CI. Its tag must be `vX.Y.Z`; it refuses
missing/inaccessible or already-published releases. Verify the draft's
attestations and notes first. The confirmation prompt is a convenience, not
authorization: Task's `--yes` can bypass it, and agents must not invoke this
operator workflow.

Stale archives remain errors. No release task automatically deletes prior
products or overwrites the capability ZIP; remove only identified stale build
files before intentionally rebuilding. A fork must review the fixed repository
coordinate in `release:publish` before adopting this toolkit-specific task.

1. Update maintainer Python, catalog, root APM, and every APM bundle version together; run
   `task profiles:build` so the compact profile manifests pin that release.
2. Add a dated changelog entry and migration/rollback guidance.
3. Audit existing delivery before intentionally regenerating APM-owned output.
4. Run the same local/CI gates and `task apm:smoke`. The smoke checks APM
   delivery of composed source packages, not resolution of a published profile
   dependency closure; see [compatibility](compatibility.md#package-boundaries).
5. Build both packages' current wheels and source distributions, plus the
   fullstack-plus-IaC source ZIP. Each distribution uses its own package version.
6. Run `uv run --locked python -m scripts.checks.release`; it checks exact inventory, metadata, licenses,
   source ZIP provenance, produces basename-only `build/SHA256SUMS`, and stages
   the verified flat inventory in `build/release/` for upload.
7. Run `uv run --locked python -m scripts.checks.governance --publication`
   and obtain independent review.

Stale or extra build products fail the release check instead of being uploaded
through a permissive wildcard. Remove only identified old artifacts deliberately.
The preparation commands do not initialize version control or push tags.
The explicitly confirmed `release:publish` task is the final remote operator step.

## Local product boundaries

The exact inventory contains:

- `agent_kit-<toolkit-version>-py3-none-any.whl` and
  `agent_kit-<toolkit-version>.tar.gz`: retained internal maintainer artifacts,
  **not PyPI products**. The root sdist is not the independently usable runtime.
- `platform_kit_runtime-<runtime-version>-py3-none-any.whl` and
  `platform_kit_runtime-<runtime-version>.tar.gz`: the standalone runtime package,
  built from `packages/runtime`, with its own metadata and license.
- `agent-kit-fullstack-iac-<toolkit-version>.zip`: composed APM source with
  independently verified source identity, inventory, and provenance.

All five products receive basename-only checksums and are copied into the same
verified local staging directory. Nothing is removed from the maintainer inventory.
To build just the runtime locally, use
`uv build --package platform-kit-runtime --out-dir <new-empty-directory>`.
The complete release checker still requires all five products under
`build/distributions` and `build/capabilities`; it does not accept an arbitrary
wheel glob or a partial runtime-only inventory.

Runtime validation compares implementation and typing-marker bytes against
canonical source, and requires the sdist's source, README, identity/AI docs,
license, and complete build recipe. Hatchling also copies the nearest
`.gitignore` into a workspace-built sdist; validation requires its exact canonical
bytes and never trusts an ignore file outside the repository.
Both formats must match name, version,
MIT license, Python requirement, dependency ranges, and optional-extra gates.
The dependency comparator supports the current range requirements and single
extra markers; unsupported requirement syntax fails closed rather than guessing.
Missing, duplicate, stale, extra, or changed files prevent checksum preparation;
changes between checksum creation and staging also fail.

These are local preparation checks, not an isolated runtime execution test,
hosted attestation, or authorization to publish. Runtime installation and
optional-import behavior remain covered by the runtime owner's package tests.

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
The independently built runtime is now included in the checked artifact set.
This does not configure runtime PyPI publication or make the maintainer package
a public Python product.

The operator checks the draft, verifies the tag/source and attestation, then
publishes intentionally. If an identically named release already exists, the
creation command fails instead of overwriting it.

## Verify artifacts

- `SHA256SUMS` detects byte corruption when obtained from a trusted source.
- It is not a signature or proof of publisher identity, but the release workflow
  attests it with the distributions and source ZIP (a governance check requires this).
- Before `task release:publish`, download the draft assets and verify each one;
  the publish task does not download assets, so this step is manual:

  ```text
  gh release download vX.Y.Z --repo lfr-ai/agent-kit --dir <empty-temp-dir>
  gh attestation verify <file> --repo lfr-ai/agent-kit   # each .whl, .tar.gz, .zip and SHA256SUMS
  sha256sum --check SHA256SUMS                           # inside the same directory
  ```

  Add `--signer-workflow lfr-ai/agent-kit/.github/workflows/toolkit-release.yml` to pin the
  signing workflow. Do not trust an unattested local build as hosted evidence.
- SBOM: not generated for the toolkit release; see
  [dependency-security.md](dependency-security.md#tool-selection-without-duplicate-gates).
- Preserve the previous source revision, locks, and selected package for rollback.
- Document corrective releases; do not replace bytes in an already published version.

Reference: [artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations),
[reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows),
[Commitizen bump flags](https://commitizen-tools.github.io/commitizen/commands/bump/),
[changelog preview](https://commitizen-tools.github.io/commitizen/commands/changelog/),
[draft creation flags](https://cli.github.com/manual/gh_release_create) and
[publishing an existing draft](https://cli.github.com/manual/gh_release_edit).
