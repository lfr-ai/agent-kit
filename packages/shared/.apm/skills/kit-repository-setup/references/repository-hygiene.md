# Repository hygiene and hosted settings

These files and settings keep every contributor's checkout, editor, hooks and
review rules consistent. Each item below states what to add, why, and how to
verify it. Review date: 2026-10-23.

## Text handling

| File | Minimum content | Why |
| --- | --- | --- |
| `.editorconfig` | `root = true`; `[*]` with `charset = utf-8`, `end_of_line = lf`, `insert_final_newline = true`, `trim_trailing_whitespace = true`, `indent_style = space`; per-language `indent_size` | editors agree before any formatter runs |
| `.gitattributes` | `* text=auto eol=lf`; `*.png binary` and other binary types; `*.bat`/`*.cmd` with `eol=crlf` if present | stops line-ending churn across operating systems |
| `.gitignore` | language caches, virtual environments, build output, coverage, `.env` and `.env.*` with `!.env.example` | keeps generated files and secrets out |

Markdown keeps trailing whitespace only when the project uses two-space line
breaks; prefer not to.

## Hooks

Use pre-commit for fast, file-scoped checks at commit time. Start from the
[hygiene hook template](../assets/pre-commit-config.yaml.template), which
covers file hygiene, private keys, secrets, spelling, Markdown, and workflow
linting. Language linters and the full gate come from the repository's own
gate definition so hooks and CI share one version (see the `kit-verify-change`
skill for ordering and parity).

- Freeze every `rev` to a full commit SHA with the version as a comment
  (`pre-commit autoupdate --freeze`); the template uses `REVIEWED_COMMIT_SHA`
  placeholders that must be replaced.
- Keep the default stage under about ten seconds; put link checks and the
  full gate in the `manual` stage.
- Install `commit-msg` hooks only when commit linting is enforced in CI too.

## Dev container

A dev container makes "works on my machine" reproducible and is the clean
environment for testing the README quick start. Start from the
[dev container template](../assets/devcontainer.json.template):

- Pin the base image by digest and each feature by exact version; let the
  dependency bot update both.
- Run the bootstrap command (install from the lockfile) in
  `updateContentCommand` or `postCreateCommand`; never `curl | sh`.
- Recommend only extensions that match the committed tools.
- Do not mount host credentials or the Docker socket unless the workflow needs
  them, and document why.

## Spelling

CSpell checks prose and identifiers. Start from the
[CSpell template](../assets/cspell.json.template):

- Keep project vocabulary in dictionary files under `.cspell/` (one for
  project terms, one for people and product names), never in an inline
  `words` array that grows without review.
- Enable language dictionaries for the languages in use.
- Ignore generated paths and lockfiles; fix typos instead of adding them.

## Branch rulesets (operator action)

Propose, do not apply. A ruleset for the default branch typically:

- requires pull requests with at least one approving review and code owner
  review, dismisses stale approvals and requires conversation resolution;
- requires the gate's status checks by name, with branches up to date;
- blocks force pushes and deletion, and requires linear history if the
  project squashes or rebases;
- optionally requires signed commits;
- applies to administrators, with a named, audited bypass list.

Protect release tags (`v*`) with a tag ruleset that blocks updates and
deletion.

## Release automation

Prefer a tag-driven workflow that builds once, attests the artifacts and
publishes with trusted publishing, behind an environment with required
reviewers. Version and changelog proposals come from Conventional Commits
tooling; the release decision stays with an operator. The `kit-release` skill
owns the procedure and its workflow template.

## OpenSSF Scorecard

Scorecard scores repository practices. Use its checks as a checklist even
without running the hosted action:

| Check | What satisfies it |
| --- | --- |
| Security-Policy | `SECURITY.md` with a private channel |
| License | a recognized license file |
| Dependency-Update-Tool | one configured update bot |
| Pinned-Dependencies | actions by SHA, images by digest, locked installs |
| Token-Permissions | top-level `permissions: {}` or read-only, widened per job |
| Dangerous-Workflow | no untrusted checkout in `pull_request_target`, no script injection |
| Branch-Protection, Code-Review | the ruleset above, enforced |
| CI-Tests, SAST | a gate and static analysis on every pull request |
| Signed-Releases, Packaging | attested artifacts published by a workflow |
| Binary-Artifacts | no committed executables |
| Vulnerabilities, Maintained, Fuzzing, CII-Best-Practices | ongoing practice; report honestly |

Running the Scorecard action and publishing results is an operator decision.

## Optional hosted advisories

CodeRabbit (review comments) and Codecov (coverage reports) can add signal.
Treat both as advisory: the local gate and its thresholds remain the
authority, configuration files contain no tokens, and installing the hosted
app is an operator action. If adopted, set Codecov status checks to
informational until the local threshold and the hosted one agree.

## Primary sources

- [EditorConfig](https://editorconfig.org/)
- Git, [gitattributes](https://git-scm.com/docs/gitattributes)
- [pre-commit](https://pre-commit.com/)
- [Development Containers specification](https://containers.dev/implementors/json_reference/)
- CSpell, [configuration](https://cspell.org/docs/Configuration)
- GitHub, [About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
- GitHub, [Security hardening for GitHub Actions](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions)
- OpenSSF, [Scorecard checks](https://github.com/ossf/scorecard/blob/main/docs/checks.md)
- [CodeRabbit documentation](https://docs.coderabbit.ai/) and [Codecov documentation](https://docs.codecov.com/)
