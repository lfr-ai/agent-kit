# Community health files

Community health files tell a visitor what the project is, how to use it, how
to contribute, how to report a vulnerability and who decides. GitHub surfaces
several of them in the repository sidebar and in the new-issue flow. Review
date: 2026-10-23.

## Inventory

| File | Location | Required for | Content owner |
| --- | --- | --- | --- |
| `README.md` | root | every repository | maintainers |
| `LICENSE` | root | any public code; a repository without one is "all rights reserved" | legal owner of the code |
| `CONTRIBUTING.md` | root, `.github/` or `docs/` | accepting outside changes | maintainers |
| `CODE_OF_CONDUCT.md` | root, `.github/` or `docs/` | any public community | maintainers; name a private reporting channel |
| `SECURITY.md` | root, `.github/` or `docs/` | any published code | security contact |
| `SUPPORT.md` | root, `.github/` or `docs/` | public projects with users | maintainers |
| `GOVERNANCE.md` | root or `docs/` | more than one maintainer, or a foundation | maintainers |
| `CODEOWNERS` | `.github/`, root or `docs/` | required review by owners | maintainers |
| Issue forms | `.github/ISSUE_TEMPLATE/*.yml` plus `config.yml` | structured bug and feature reports | maintainers |
| Pull request template | `.github/pull_request_template.md` | consistent review evidence | maintainers |
| `CHANGELOG.md` | root | released software | release owner (see the `kit-documentation` skill) |

An organization can provide defaults from a public `.github` repository; a
file in the repository itself always wins. Prefer files in the repository so
they travel with forks and archives.

## README style

- Open with one sentence: what the project is and who it is for.
- Put **Quick start** next: prerequisites with versions, install from the
  lockfile, one command that proves the setup works, and the expected result.
- Then usage with synthetic data, links to deeper documentation,
  development commands, support, security and license.
- Write plainly in the second person or imperative. No emojis, no badge walls
  (at most build, release and license), no superlatives such as "blazing" or
  "revolutionary", no claims the tests do not prove.
- Keep it short; move long explanations to linked pages. A README that needs a
  table of contents is doing too much.
- Every command is copied from the source of truth (Taskfile, `pyproject.toml`)
  and was run, or is labeled illustrative.

## Content rules per file

- **LICENSE**: the unmodified license text with the copyright line. Pick with
  the legal owner; record the SPDX identifier in package metadata as well.
- **CONTRIBUTING**: setup command, test and gate commands, branch and commit
  conventions, review expectations, how to propose large changes first, and
  the license of contributions (inbound equals outbound, or a sign-off rule
  such as the Developer Certificate of Origin).
- **CODE_OF_CONDUCT**: adopt a published code (for example the Contributor
  Covenant) by reference or verbatim with its license, and add a private
  reporting contact that is not a personal address in a portable template.
- **SECURITY**: supported versions, private reporting channel (GitHub private
  vulnerability reporting first), what to include, expected response times as
  intentions rather than guarantees, and coordinated disclosure.
- **SUPPORT**: where to ask questions, what is out of scope, and that the
  issue tracker is not for vulnerabilities.
- **GOVERNANCE**: roles, how decisions are made, how maintainers are added
  and removed, and how the code of conduct is enforced.
- **CODEOWNERS**: map paths to teams rather than individuals where possible;
  the last matching pattern wins. Owners must have write access or the rule
  is silently ignored. Cover the CODEOWNERS file and workflow files themselves.
- **Issue forms**: YAML forms with required fields for version, reproduction
  and expected result; `config.yml` sets `blank_issues_enabled: false` and
  links security reports to the private channel.
- **Pull request template**: summary, linked issue, test evidence (commands
  and results), breaking changes, and a short checklist that matches the gate.

## Anti-patterns

- Copying another project's files and leaving its name, contacts or claims.
- A SECURITY file that asks reporters to open a public issue.
- Placeholder text (`TODO`, `your-org`) shipped in a published repository.
- A README whose quick start depends on undeclared global tools.
- CODEOWNERS entries for people who lack write access.

## Verification

1. Run [check_repository_files.py](../assets/check_repository_files.py) with
   `--root .`.
2. Open the repository's community profile page
   (`https://github.com/OWNER/REPO/community`) as an operator check.
3. Follow the README quick start in a clean container or dev container.
4. Confirm the issue chooser shows the forms and the security link.

## Primary sources

- GitHub, [Creating a default community health file](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file)
- GitHub, [About code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
- GitHub, [Syntax for issue forms](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms)
- GitHub, [Creating a pull request template](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository)
- GitHub, [Adding a security policy](https://docs.github.com/en/code-security/getting-started/adding-a-security-policy-to-your-repository)
- [Contributor Covenant](https://www.contributor-covenant.org/)
- [Developer Certificate of Origin](https://developercertificate.org/)
- [Choose a License](https://choosealicense.com/) and [SPDX License List](https://spdx.org/licenses/)
