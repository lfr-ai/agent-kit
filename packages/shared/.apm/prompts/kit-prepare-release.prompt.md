---
description: Prepare a release candidate locally by choosing the version, editing the changelog, and building and inspecting artifacts, without publishing.
argument-hint: Optional target version or release scope
agent: agent
---

# Prepare a release candidate

Get a release ready for an authorized operator. Tagging, pushing, and
publishing are publication steps and are out of scope for this prompt.

## Input

- The user-supplied argument may give the intended version or scope. When it
  is empty, derive a proposal from the history since the last release tag.

## Procedure

1. Load [kit-release](../skills/kit-release/SKILL.md) and copy its release
   checklist for this candidate.
2. Read the release policy, the single version source, supported targets, and
   who owns publication.
3. List commits since the last tag and classify them with
   [Conventional Commits](../skills/kit-release/references/conventional-commits.md).
   Treat any automated bump as a proposal.
4. Choose the next version with the [SemVer rules](../skills/kit-release/references/semver.md);
   name every breaking change and deprecation that drives the choice.
5. Edit the changelog section for users: what changed, what to do, and
   migrations. Check every claim against shipped content.
6. Align the version and license across package metadata and manifests.
7. Build into a fresh, contained output directory with the locked toolchain.
   Inspect the artifacts for secrets, private files, build debris, and missing
   license notices. Install from the artifact outside the source tree and run
   a smoke command.
8. Generate checksums for exactly the files that would be published.
9. Run the declared completion and release checks on the candidate commit and
   record each result or skipped prerequisite.
10. Write the operator handoff: tag name, tag message, artifacts, checksums,
    and the rollback version.

## Acceptance gates

- [ ] One version appears consistently in manifests and the changelog.
- [ ] Artifacts were built clean and installed outside the source tree.
- [ ] Checksums match the files listed for publication.
- [ ] No tag was pushed and nothing was published by this prompt.

## Output

The proposed version with its reason, the changelog section, a checklist table
(check, command, result), artifact list with checksums, and the operator
handoff steps.
