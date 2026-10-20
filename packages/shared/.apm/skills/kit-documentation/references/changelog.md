# Changelog: Keep a Changelog

A changelog tells users what changed between releases in terms they care about.
It is written for people, not generated verbatim from commit messages.

## Format

`CHANGELOG.md` at the repository root, newest release first:

```markdown
# Changelog

All notable changes to this project are documented in this file.
The format is based on Keep a Changelog, and this project adheres to
Semantic Versioning.

## [Unreleased]

### Added

- Invoice export accepts a `--since` date filter.

## [1.4.0] - 2026-05-02

### Fixed

- Order totals no longer round twice when a discount applies.

[Unreleased]: https://example.com/shop/compare/v1.4.0...HEAD
[1.4.0]: https://example.com/shop/compare/v1.3.2...v1.4.0
```

Rules:

- An `Unreleased` section at the top collects changes as they merge. At release
  it is renamed to the version and date, and a new empty `Unreleased` starts.
- One section per version: `## [x.y.z] - YYYY-MM-DD` with ISO dates.
- Change types, in this order, only those that apply: **Added**, **Changed**,
  **Deprecated**, **Removed**, **Fixed**, **Security**.
- Each entry is one line describing the effect for a user; link to the issue or
  pull request when helpful.
- Breaking changes are stated plainly and say what users must do.
- Versions are links to a comparison of tags, defined at the bottom.
- Yanked releases stay listed with `[YANKED]` after the date.

Start from the [changelog template](../assets/CHANGELOG.md.template).

## What belongs in it

| Include | Leave out |
| --- | --- |
| new features, options, endpoints | refactorings with no visible effect |
| changed defaults or behavior | dependency bumps without user impact |
| deprecations with the planned removal version | CI and tooling changes |
| removals and their replacements | typo fixes in code comments |
| user-visible bug fixes | internal renames |
| security fixes (without exploit details before disclosure) | merge commits |

## Relationship to commit messages

Conventional Commits make changelog drafting easier: `feat` maps to Added,
`fix` to Fixed, a `!` or `BREAKING CHANGE:` footer to a breaking-change note.
A generator (for example commitizen's `cz changelog` or `cz bump --changelog`)
can produce the draft. Still read and edit the draft:

- Merge several commits for one feature into one entry.
- Rewrite developer phrasing into user-facing language.
- Drop entries users cannot observe.
- Check that each breaking change says what to do.

The release skill, when installed, covers version bumps and tagging.

## Alternatives for busy repositories

When many pull requests edit the `Unreleased` section at once, conflicts pile
up. Use one fragment file per change (for example `changes/1234.added.md`)
collected into the changelog at release time by a fragment tool such as
towncrier or scriv. The published changelog keeps the same format.

## Sources

- [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)
- [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)
- [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)
- [commitizen: changelog](https://commitizen-tools.github.io/commitizen/commands/changelog/)
- [towncrier](https://towncrier.readthedocs.io/)
