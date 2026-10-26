# Dependency selection, naming and removal

Review date: 2026-10-23. Record the evidence you collect with its date and
source URL in the [adoption review](../assets/dependency-adoption-review.md.template)
so a later reviewer can re-check it.

## First question: do you need it

| Need | Prefer | Add a dependency only when |
| --- | --- | --- |
| Small utility (retry, slugify, parsing a simple format) | standard library or a few local lines with tests | the edge cases are a known source of bugs (dates, time zones, Unicode, cryptography) |
| A capability another locked dependency already provides | the existing dependency | the existing one is abandoned or unsafe |
| Security-sensitive primitive (cryptography, password hashing, TLS, parsing untrusted formats) | a well-reviewed, widely deployed library | always; never hand-roll these |
| Development-only tool | a pinned entry in a development group | the tool runs only in development and CI |

## Admission criteria

Reject a package that fails a hard limit, however popular it is.

| Criterion | Evidence | Hard limit |
| --- | --- | --- |
| Maintenance | last release date; issues and security reports answered | a release or documented maintenance status within the last 18 months |
| Maintainers | people or organization with publish rights; recent commit authors | more than one person can publish, or an organization owns the project |
| Release cadence | release history; changelog; semantic versioning | releases are tagged and described; no unexplained version jumps |
| Adoption | dependents and download trends (deps.dev, pypistats, npm) | none on its own; low adoption raises the bar for every other row |
| License | SPDX identifier in metadata and the license file | on the project's allow-list |
| Security posture | OpenSSF Scorecard; security policy; signed or attested releases | a documented way to report vulnerabilities |
| Install-time code | wheels for target platforms; npm lifecycle scripts | no install script, or one that was read and accepted |
| Footprint | new transitive packages (`uv tree --package <name>`, `npm ls`) | each transitive package is acceptable under the same rules |

Scorecard checks that matter most for admission: Maintained, Code-Review,
Branch-Protection, Signed-Releases, Pinned-Dependencies, Token-Permissions,
Dangerous-Workflow, Vulnerabilities and Security-Policy. Treat the aggregate
score as a prompt for questions, not a pass mark. Stars, forks and download
counts can be bought or inflated and never approve a package by themselves.

## Verify the name and the source

Attackers publish packages whose names are one keystroke, one separator or one
plausible guess away from a real one, and code assistants sometimes suggest
package names that do not exist until an attacker registers them.

1. Copy the name from the project's own documentation or repository, not from
   memory, a chat answer or a search snippet.
2. Open the index page and confirm the repository link, the maintainers and
   the release history agree. A repository link on an index page is a claim;
   check that the repository links back to that package.
3. Compare against near-miss names: separators (`-`, `_`, `.`), plurals,
   transposed letters, and a famous name with a prefix or suffix.
4. Be suspicious of a brand-new package, a first release with a high version
   number, or an old name whose ownership changed recently.

## Dependency confusion

An internal package name that also exists on a public index can be replaced by
the public one when a resolver searches both and prefers the higher version.

- uv's default index strategy (`first-index`) takes each package from the first
  index that contains it; keep that default. Mark private indexes
  `explicit = true` and route internal packages to them with
  `[tool.uv.sources]`.
- Never combine a private index with the public one through pip's
  `--extra-index-url`; pip merges candidates from all indexes.
- For npm, publish internal packages under an organization scope and map that
  scope to the private registry in the project `.npmrc`.
- Register placeholder names on the public index for internal names that must
  never resolve there, when the organization's policy allows it.

## Install-time code

- Python source distributions run a build backend on install. Prefer wheels;
  in CI install with `--no-build` (uv) or `--only-binary :all:` (pip) once the
  lock has wheels for every target.
- npm runs lifecycle scripts by default; set `ignore-scripts=true` and allow
  only reviewed packages. Bun runs dependency lifecycle scripts only for
  packages listed in `trustedDependencies`.

## Removing unused dependencies

1. Run deptry for Python (`deptry .`): `DEP002` reports declared but unused
   packages, `DEP001` missing ones, `DEP003` transitive imports and `DEP004`
   development packages imported by production code. Use the ecosystem's
   equivalent for JavaScript.
2. Confirm each finding by hand: plugins loaded by entry points, optional
   imports, command-line tools invoked from scripts and type-stub packages are
   invisible to import analysis.
3. Remove the declaration, regenerate the lock (`uv remove --no-sync <name>` then audit),
   run the full gate, and note the removal in the change summary.

## Primary sources

Reviewed 2026-10-23.

- OpenSSF, [Concise guide for evaluating open source software](https://best.openssf.org/Concise-Guide-for-Evaluating-Open-Source-Software)
- OpenSSF, [Scorecard](https://scorecard.dev/) and [check documentation](https://github.com/ossf/scorecard/blob/main/docs/checks.md)
- Open Source Insights, [deps.dev](https://deps.dev/)
- uv, [Package indexes and index strategies](https://docs.astral.sh/uv/concepts/indexes/)
- PyPA, [Secure installs with pip](https://pip.pypa.io/en/stable/topics/secure-installs/)
- Bun, [bun install and lifecycle scripts](https://bun.com/docs/pm/cli/install)
- deptry, [Documentation](https://deptry.com/)
- OpenSSF, [Malicious packages repository](https://github.com/ossf/malicious-packages)
