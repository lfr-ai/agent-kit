# Supply chain: pinning, updates, caches, and attestations

## Pin actions to full commit SHAs

A tag such as `v4` or a branch such as `main` is mutable: the action owner, or
anyone who compromises the owner's account, can move it. A full 40-character
commit SHA is the only immutable reference for a repository action.

- Pin every third-party action and reusable workflow as
  `owner/repo@<40-hex-sha> # vX.Y.Z`. The trailing comment keeps the human
  version visible and lets Dependabot update both together.
- Short SHAs are not immutable references; always use the full SHA.
- Verify the SHA belongs to the action's own repository, not a fork network
  object, by resolving it from the upstream tag before pinning.
- Pin container actions (`docker://`) and job `container:` images by digest
  (`image@sha256:...`).
- Organization policy can require SHA pinning for all actions and restrict
  which actions are allowed; enable it where available and record exceptions.
- Actions in the same repository (`./path`) are reviewed with the change and
  need no pin. Actions owned by your organization may be exempted by policy;
  pass `--trusted-owner` to the checker to encode that policy explicitly.

## Keep pins current with Dependabot

Pinned SHAs only stay safe if they are updated. Configure the
`github-actions` ecosystem so Dependabot proposes SHA bumps with the new
version comment. Group minor and patch updates to reduce noise, keep majors
separate, and use a 14-day cooldown so brand-new releases age before adoption.
See [the Dependabot template](../assets/templates/dependabot.yml.template).

## Cache and artifact integrity

- Caches are scoped by branch: a pull request can read caches from its base
  branch but writes only to its own ref. Still, never restore a cache into a
  privileged job when the cache key could have been written by an untrusted run.
- Include lockfile hashes in cache keys so a dependency change cannot reuse a
  stale or tampered cache.
- Do not cache credentials, `.npmrc` files with tokens, or cloud login state.
- Set short `retention-days` on artifacts and never upload workspace roots that
  may contain `.git/config` credentials written by checkout. Use
  `persist-credentials: false` on checkout when later steps do not push.

## Artifact attestations

Build provenance attestations bind an artifact digest to the workflow, commit,
and runner that produced it, signed with a short-lived Sigstore certificate.

- The attesting job needs `id-token: write` and `attestations: write`
  (plus `packages: write` when pushing an image attestation to a registry).
- Attest the exact digest that is published; attesting a file and then
  rebuilding it breaks the chain.
- Consumers verify with `gh attestation verify <artifact> --repo <owner>/<repo>`
  (or `--owner`), optionally constraining the signer workflow.
- Attestations prove where and how an artifact was built. They do not prove
  the source was safe; combine them with review and dependency scanning.
- For SBOMs, generate the document during the build and attest it with the
  SBOM attestation action so the SBOM is bound to the same digest.

## Dependency review and audits

- Run dependency review on pull requests to block newly introduced packages
  with known vulnerabilities or disallowed licenses. Set `fail-on-scopes` to
  `runtime, development, unknown`, keep `fail-on-severity` at `low`, and list
  allowed SPDX licenses in `allow-licenses` (`deny-licenses` is deprecated).
- Dependency review only inspects a pull request's diff. Also audit the whole
  lockfile on a schedule, because advisories are published after merge. Use the
  [dependency audit template](../assets/templates/dependency-audit.yml.template)
  and call it from the required CI summary.
- Audit before installing: install only the hash-locked audit tools, audit the
  exported lock, then sync. Install dependencies with `--no-build` so a package
  without a wheel cannot run its build backend on the runner.
- Keep cooldowns for version updates only. A global resolver cutoff such as uv's
  `exclude-newer` also blocks a same-week security fix; prefer Dependabot
  cooldowns plus immediate security updates.
- Enable secret scanning and push protection at the repository level.

## Reusable workflows in the same repository

Call same-repository actions and reusable workflows with `uses: $/...` instead of
`./...`. The self-repository form resolves at the running commit, does not depend
on files a previous step checked out, and counts as pinned for SHA-pinning policy.

## Hook and tool pins

- Pin pre-commit hook repositories to full commit SHAs with a `# frozen: vX`
  comment (`pre-commit autoupdate --freeze`); a tag can be moved.
- Pin container images that hooks or jobs run by digest.
- Lint workflows with zizmor in pre-commit or CI; it detects template injection,
  credential persistence, cache poisoning, and unpinned references.
- Use the [zizmor policy template](../assets/templates/zizmor.yml.template) as
  `.github/zizmor.yml`. Both zizmor and CodeRabbit discover it automatically;
  it sets a minimum 14-day Dependabot default cooldown without disabling rules.
  SHA pinning uses zizmor's default policy. `--config` is only needed for a
  nonstandard location.
  Ensure policy-only edits rerun the actual workflow scan.
- actionlint discovers `.github/actionlint.yaml` or `.yml`. Its CodeRabbit
  integration documents default configuration only, so native hook results
  remain authoritative for reviewed local exceptions.
- Never add vulnerability or secret-scan exclusions just to create a config
  file. Native OSV config is local to each scanned file's directory; Gitleaks
  config and detect-secrets baselines have different discovery semantics.

## Review checklist

- [ ] Every external `uses:` is pinned to a full SHA with a version comment.
- [ ] Same-repository references use `$/` self-repository syntax.
- [ ] Dependabot covers the `github-actions` ecosystem and every lockfile.
- [ ] Pull requests run dependency review for vulnerabilities and licenses.
- [ ] The full lockfile is audited before installation and on a schedule.
- [ ] Cache keys include lockfile hashes; privileged jobs do not restore
      caches writable by untrusted runs.
- [ ] Checkout uses `persist-credentials: false` unless a later step pushes.
- [ ] Published artifacts carry provenance attestations for their digests.

## Sources

- <https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions>
- <https://docs.github.com/en/code-security/dependabot/working-with-dependabot/keeping-your-actions-up-to-date-with-dependabot>
- <https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference>
- <https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds>
- <https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/caching-dependencies-to-speed-up-workflows>
- <https://github.com/actions/dependency-review-action>
- <https://github.com/pypa/pip-audit>
- <https://docs.astral.sh/uv/reference/settings/#no-build>
- <https://github.blog/changelog/2026-07-30-reference-same-repository-actions-with-self-repository-syntax/>
- <https://pre-commit.com/#pre-commit-autoupdate>
- <https://docs.zizmor.sh/>
- <https://docs.zizmor.sh/configuration/>
- <https://docs.coderabbit.ai/tools/zizmor>
- <https://docs.coderabbit.ai/tools/actionlint>
