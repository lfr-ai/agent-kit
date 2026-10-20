# Conventional Commits and commitizen

Conventional Commits give commit messages a machine-readable shape so the next
version and a changelog draft can be derived from history.

## Message format

```text
<type>[optional scope][!]: <description>

[optional body]

[optional footer(s)]
```

- `feat`: a new feature; implies a MINOR bump.
- `fix`: a bug fix; implies a PATCH bump.
- `!` after the type or scope, or a `BREAKING CHANGE: <explanation>` footer:
  implies a MAJOR bump (or MINOR while `major_version_zero` is on).
- Other common types with no version effect by default: `docs`, `refactor`,
  `perf`, `test`, `build`, `ci`, `chore`, `style`, `revert`.
- Scope names the area: `feat(invoices): add CSV export`.
- Footers follow Git trailer format: `Refs: #123`, `Co-authored-by: ...`.

Good messages describe the effect, in the imperative: `fix(orders): reject
negative quantities`, not `fixed bug` or `changes`.

## commitizen

[commitizen](https://commitizen-tools.github.io/commitizen/) validates
messages, computes the next version from commit history, updates version
files, creates the tag and can generate the changelog.

Configuration lives in the first file found among `.cz.toml`, `cz.toml`,
`.cz.json`, `cz.json`, `.cz.yaml`, `cz.yaml` and `pyproject.toml`
(`[tool.commitizen]`). Keep exactly one. The
[commitizen template](../assets/cz.toml.template) is a commented starting point;
copy it to `.cz.toml` and adjust.

Key options:

| Option | Meaning |
| --- | --- |
| `name` | commit rules; `cz_conventional_commits` for Conventional Commits |
| `version_provider` | where the version lives: `commitizen` (in the config), `pep621` or `uv` (`pyproject.toml`), `npm`, `cargo`, `scm` (tags only) |
| `version_scheme` | `semver2` or `pep440` formatting of pre-releases |
| `tag_format` | for example `v$version` |
| `version_files` | other files whose version string is updated, as `path:regex` |
| `major_version_zero` | keep breaking changes in `0.y` instead of jumping to `1.0.0` |
| `update_changelog_on_bump` | regenerate the changelog during `cz bump` |
| `changelog_incremental` | only add new sections; keep hand edits to older ones |
| `annotated_tag` / `gpg_sign` | create annotated or signed tags on bump |
| `bump_message` | commit message used for the bump commit |

Commands:

```text
cz commit                 # interactive message builder
cz check --rev-range origin/main..HEAD   # validate messages in a range
cz bump --dry-run         # show the next version and files it would change
cz bump                   # update versions, commit and tag (local only)
cz changelog --dry-run    # print the generated changelog
```

`cz bump` changes files, creates a commit and a tag **locally**. Pushing the
commit and tag is a separate, operator-approved step.

## Enforcing the format

- A `commit-msg` hook (`cz check --commit-msg-file`) through the repository's
  pre-commit configuration gives fast feedback.
- CI re-checks the pull request range because hooks can be skipped.
- With squash merges, only the pull request title becomes the commit on the
  main branch; validate the title instead of every commit.

## From commits to a release

1. Merge changes with conventional messages.
2. Run `cz bump --dry-run` and review the proposed version against the
   [SemVer rules](semver.md). The tool infers from messages; a mislabelled
   breaking change still breaks users.
3. Draft the changelog, then edit it for users (merge related entries, drop
   invisible ones, explain breaking changes).
4. Run `cz bump` (or bump by hand) to update version files and create the tag.
5. Follow [tagging and signing](tagging.md) and the
   [release workflow](release-workflow.md).

## Sources

- [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)
- [commitizen configuration file](https://commitizen-tools.github.io/commitizen/config/configuration_file/)
- [commitizen configuration settings](https://commitizen-tools.github.io/commitizen/config/option/)
- [commitizen bump](https://commitizen-tools.github.io/commitizen/commands/bump/)
- [git-interpret-trailers](https://git-scm.com/docs/git-interpret-trailers)
