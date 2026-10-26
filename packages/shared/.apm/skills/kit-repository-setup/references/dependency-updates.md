# Dependency update automation

One bot proposes dependency updates as reviewable pull requests. Two bots
fighting over the same manifest produce duplicate pull requests, conflicting
lockfiles and review fatigue. Review date: 2026-10-23; check option names
against the current documentation before adopting.

## Choose one manager

| Need | Dependabot | Renovate |
| --- | --- | --- |
| Hosting | built into GitHub; no app to install | GitHub app, self-hosted runner, or other forges (GitLab, Bitbucket, Azure DevOps, Forgejo) |
| Security alerts linked to pull requests | native (Dependabot alerts and security updates) | via OSV or the platform's vulnerability data, depending on setup |
| Ecosystem breadth | common ecosystems, including uv, pre-commit, devcontainers, Docker, GitHub Actions | broader, plus custom regex managers for versions in arbitrary files |
| Grouping | `groups` by pattern, dependency type, update type | `packageRules` with `groupName`, presets such as monorepo groups |
| Release-age delay | `cooldown` (`default-days`, per semver level) | `minimumReleaseAge` per rule |
| Schedule | `schedule.interval`, day, time, timezone | `schedule` with natural-language windows |
| Lockfile refresh | updates lockfiles with manifests | also `lockFileMaintenance` for transitive refreshes |
| Dashboard | none | dependency dashboard issue |
| Configuration sharing | per repository | shareable presets |

Decision:

- **Default to Dependabot** for a GitHub repository whose ecosystems it
  supports: least moving parts and native security updates.
- **Choose Renovate** when the repository is not on GitHub, needs custom
  managers (versions in Dockerfiles, scripts or docs), needs shared presets
  across many repositories, or needs `lockFileMaintenance`.
- **Run both only for a documented gap**: for example Dependabot security
  alerts only (no version updates) plus Renovate version updates, with each
  ecosystem owned by exactly one bot. Write the split in the configuration
  comment.

## Configuration rules

- **Group** minor and patch updates per ecosystem and dependency type; keep
  major updates and tools that need a compatibility check in their own pull
  request.
- **Separate security updates** from version updates so they are never
  blocked by a group that fails for unrelated reasons.
- **Schedule** weekly in a quiet window with a pull request limit, so review
  happens in batches.
- **Delay new releases** (three to fourteen days) so compromised or broken
  releases are usually yanked before they reach you; security fixes skip the
  delay.
- **Pin and digest**: actions by commit SHA with a version comment, images by
  digest, hooks by frozen revision; the bot updates the pin and the comment.
- **Commit messages** follow the repository's convention (for example
  Conventional Commits `build(deps):`, `ci(deps):`) so commit linting passes.
- **Labels** identify bot pull requests for filtering and required checks.
- **Never auto-merge** without required checks, and never for major updates
  or for packages that run code at install time without review.

## Anti-patterns

- Version ranges in manifests "so the bot has less to do"; the lockfile then
  drifts silently.
- One giant weekly group that mixes runtime majors with tool patches.
- Ignoring a package forever instead of recording why and when to revisit.
- Updating hook revisions outside the bot in unrelated changes.

## Verification

1. Validate the file: Dependabot reports configuration errors on the
   repository's Insights > Dependency graph page; Renovate ships
   `renovate-config-validator` (run it through the locked toolchain).
2. Confirm every manifest and lockfile directory is covered exactly once.
3. After the first run, review one grouped pull request end to end with the
   full gate.

## Primary sources

- GitHub, [Dependabot options reference](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference)
- GitHub, [About Dependabot security updates](https://docs.github.com/en/code-security/dependabot/dependabot-security-updates/about-dependabot-security-updates)
- Renovate, [Configuration options](https://docs.renovatebot.com/configuration-options/)
- Renovate, [Minimum release age](https://docs.renovatebot.com/key-concepts/minimum-release-age/)
- Renovate, [Bot comparison](https://docs.renovatebot.com/bot-comparison/)
- OpenSSF Scorecard, [Dependency-Update-Tool check](https://github.com/ossf/scorecard/blob/main/docs/checks.md#dependency-update-tool)
