---
name: kit-repository-setup
description: Use when preparing a repository for open-source or production use with community files, README, bots and hooks.
license: MIT
---

# Make a repository ready to publish and maintain

## Procedure

1. Inventory what exists before adding anything: root files, `.github/`,
   hook, editor, spelling and dependency-bot configuration. Run the
   [repository file checker](assets/check_repository_files.py) for a baseline.
   Do not generate a whole tree with a scaffolding tool; add one reviewed file
   at a time.
2. Add the missing community health files listed in the
   [community files reference](references/community-files.md): README,
   LICENSE, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, SUPPORT, GOVERNANCE,
   CODEOWNERS, issue forms and a pull request template. Start from the
   [README](assets/README.md.template), [CONTRIBUTING](assets/CONTRIBUTING.md.template)
   and [SECURITY](assets/SECURITY.md.template) templates and fill them with
   the project's own facts.
3. Write the README quick start first, plainly, without emojis, badge walls or
   marketing claims; every command must run as written.
4. Document configuration in `.env.example` following the
   [environment example rules](references/env-example.md) and the
   [template](assets/env.example.template): every variable documented and
   grouped, placeholders only, never a real value.
5. Normalize text handling with `.editorconfig` and `.gitattributes`, then add
   hooks, a dev container and spelling following the
   [repository hygiene reference](references/repository-hygiene.md), the
   [pre-commit template](assets/pre-commit-config.yaml.template), the
   [dev container template](assets/devcontainer.json.template) and the
   [CSpell template](assets/cspell.json.template). Gate ordering and CI parity
   belong to the `kit-verify-change` skill.
6. Choose one dependency update manager with the
   [dependency update decision table](references/dependency-updates.md), then
   adapt the [Dependabot](assets/dependabot.yml.template) or
   [Renovate](assets/renovate.json.template) template with grouping, a
   schedule and a release-age delay. Dependency risk review belongs to the
   `kit-supply-chain` skill.
7. Propose branch rulesets, required checks, release automation and the
   OpenSSF Scorecard checks to the repository operator; applying them changes
   remote state and is an operator action. Release candidates follow the
   `kit-release` skill.
8. Treat hosted review services (CodeRabbit, Codecov) as optional advisories;
   they never replace the local gate.
9. Re-run the checker and the repository's declared gate; report which files
   were added and which settings still need an operator.

## Acceptance gates

- `check_repository_files.py` exits 0, or every remaining finding has a
  recorded reason.
- The README opens with what the project is and a quick start that was
  executed in a clean environment, or is labeled illustrative.
- `.env.example` holds placeholders only and every variable has a comment.
- Exactly one dependency update manager is configured, with grouping, a
  schedule and a release-age delay, unless a documented gap needs a second.
- Every hook, action, image and dev container feature is pinned to an exact
  version, commit or digest; no placeholder remains in an adopted file.
- No secret, personal contact, company fact or absolute local path appears in
  a committed file.
- Remote settings (rulesets, private vulnerability reporting, Scorecard) are
  listed as operator actions, not reported as done.
