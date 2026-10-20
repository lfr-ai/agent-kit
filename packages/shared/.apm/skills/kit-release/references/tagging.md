# Tagging and signed tags

A release tag names the exact commit that was built and published. Tags are
shared, effectively permanent identifiers: treat creating and pushing one as
publication.

## Annotated, not lightweight

- **Lightweight tag**: just a name pointing at a commit. No author, date or
  message. Fine for private bookmarks, not for releases.
- **Annotated tag**: a full Git object with tagger, date and message, and it can
  be signed. Use annotated tags for releases: `git tag -a v1.4.0 -m "v1.4.0"`.
- `git describe` ignores lightweight tags by default, another reason to annotate.

Tag naming: a consistent prefix and the exact version, `v1.4.0`. Match the
bump tool's `tag_format`.

## Signing

Signing proves who created the tag and that it was not altered.

| Method | Set up | Create | Verify |
| --- | --- | --- | --- |
| OpenPGP (GPG) | `git config user.signingKey <key-id>` | `git tag -s v1.4.0 -m "v1.4.0"` | `git tag -v v1.4.0` |
| SSH key | `git config gpg.format ssh` and `user.signingKey <path-to-public-key>` | `git tag -s v1.4.0 -m "v1.4.0"` | `git tag -v v1.4.0` with `gpg.ssh.allowedSignersFile` configured |
| X.509 / keyless (for example gitsign) | tool-specific | `git tag -s` with `gpg.format x509` and the tool as program | tool-specific |

- `git config tag.gpgSign true` signs every annotated tag by default.
- On GitHub, upload the signing key (GPG key or SSH signing key) to the account
  so tags and commits show as verified. Verification on the hosting service
  is a convenience; consumers should verify with `git tag -v` and a trusted
  key list.
- Keep signing keys off shared machines; prefer hardware-backed keys. Never put
  a private signing key in a repository or a CI secret unless the release
  process is designed for it, and then scope it to a protected environment.

## Protecting tags

- Protect the release tag pattern (`v*`) with a repository ruleset that
  restricts creation, update and deletion to the release role. Unprotected tags
  can be moved, and a moved tag silently changes what a version means.
- Never delete and recreate a published tag. If a release is wrong, publish a
  new version and mark the bad one as yanked or deprecated.
- Where the hosting service offers immutable releases, enable them so release
  assets and the tag cannot change after publication.

## Local tagging procedure

1. Confirm the working tree is clean and `HEAD` is the reviewed release commit
   on the release branch.
2. Confirm the version in the manifest, the changelog heading and the planned
   tag name agree.
3. Create a signed annotated tag; verify it locally with `git tag -v`.
4. Hand the push of the tag to the approved operator workflow
   (`git push origin v1.4.0`, never `git push --tags`, which pushes every
   local tag including stray ones).

## Sources

- [Git Book: tagging](https://git-scm.com/book/en/v2/Git-Basics-Tagging)
- [git-tag](https://git-scm.com/docs/git-tag)
- [Git Book: signing your work](https://git-scm.com/book/en/v2/Git-Tools-Signing-Your-Work)
- [git-config: gpg.format and gpg.ssh.allowedSignersFile](https://git-scm.com/docs/git-config)
- [GitHub: about commit signature verification](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification)
- [GitHub: about rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
- [GitHub: immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)
