# Semantic Versioning

A version number is a promise about compatibility. Semantic Versioning
(SemVer) makes the promise explicit: `MAJOR.MINOR.PATCH`.

## The rules that matter in practice

| Change | Bump | Example |
| --- | --- | --- |
| Incompatible change to the public API | MAJOR | `2.4.1 -> 3.0.0` |
| Backward-compatible new functionality, or a deprecation | MINOR | `2.4.1 -> 2.5.0` |
| Backward-compatible bug fix | PATCH | `2.4.1 -> 2.4.2` |

- Bumping resets lower components to zero.
- A released version's contents never change. A fix is a new version.
- Pre-releases append `-` and dot-separated identifiers: `3.0.0-rc.1`. They
  sort before the release (`3.0.0-rc.1 < 3.0.0`) and promise nothing.
- Build metadata appends `+`: `3.0.0+build.17`. It is ignored for precedence.
- `0.y.z` is initial development: anything may change. Many tools treat a
  MINOR bump in `0.y` as breaking; say explicitly what your project does
  (commitizen's `major_version_zero = true` keeps breaking changes in `0.y`).
- `1.0.0` defines the public API. Ship it once users depend on you.

## Define the public API first

SemVer is meaningless until you say what is public. Write it down, for example:

- Importable names not starting with `_` in documented modules.
- Command-line flags, exit codes and machine-readable output formats.
- HTTP endpoints, request and response schemas, status codes.
- Configuration keys and their defaults.
- File formats written to disk and read back by later versions.
- Supported runtime versions and platforms.

Everything else (private modules, log wording, internal timing) can change in
any release.

## What counts as breaking

Breaking, needs MAJOR:

- Removing or renaming a public name, flag, endpoint, field or configuration key.
- Adding a required parameter or field; tightening validation so previously
  accepted input is rejected.
- Changing a default in a way that changes results for existing users.
- Changing an output format that machines parse, or an exit code.
- Dropping support for a runtime version or platform (many projects treat this
  as MINOR when announced in advance; decide and document it).

Not breaking, MINOR or PATCH:

- Adding an optional parameter with a default that preserves behavior.
- Adding a field to a response that clients ignore unknown fields of (only if
  clients are documented to ignore unknown fields).
- Fixing behavior that contradicted the documentation (PATCH), even if someone
  relied on the bug; mention it prominently.

When in doubt, treat it as breaking or keep the old behavior behind the old
name and deprecate it.

## Deprecation policy

1. Announce: mark the API deprecated in code (a warning), documentation and
   changelog, naming the replacement and the version that will remove it.
2. Keep it working for at least one MINOR release (state your period).
3. Remove it only in a MAJOR release, listed under Removed in the changelog.

## Ecosystem version rules

- **Python** packages follow PEP 440. SemVer `1.2.3` is valid as is; a
  pre-release is spelled `1.2.3rc1` (or normalized from `1.2.3-rc.1`). Build
  metadata is a local version (`+local`) and cannot be uploaded to PyPI.
- **npm** uses SemVer directly; ranges such as `^1.2.3` assume SemVer
  compatibility rules, including the special treatment of `0.y`.
- **Container images and Git tags** are free-form; use `vMAJOR.MINOR.PATCH`
  tags consistently and never move a published tag.

## Single source of the version

Keep the version in one file (for example the package manifest) and derive the
rest: tags, changelog headings, other manifests listed in the bump tool's
configuration. A release check compares them and fails on mismatch.

## Sources

- [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)
- [PEP 440: version identification](https://peps.python.org/pep-0440/)
- [Python packaging: versioning](https://packaging.python.org/en/latest/discussions/versioning/)
- [npm: about semantic versioning](https://docs.npmjs.com/about-semantic-versioning)
- [Python warnings: DeprecationWarning](https://docs.python.org/3/library/warnings.html#warning-categories)
