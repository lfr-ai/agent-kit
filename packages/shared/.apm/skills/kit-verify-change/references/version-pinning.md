# Version pinning

Pin everything that runs code in development, CI, hooks, containers or agent
integrations. A tag, range or `latest` can change under you; an exact version
plus a lockfile hash, a full commit SHA, or an image digest cannot.

## Policy by surface

| Surface | Pinned form | Updated by |
| --- | --- | --- |
| Python development tools | `name==x.y.z` in dependency groups, hashed in the lockfile | Dependabot `uv` |
| Published Python dependencies | Bounded range (`>=x,<y`) for consumers; the project lock pins the exact build | Dependabot `uv` |
| Build backend closure | `build-system` and build constraints with `==` | Manual review |
| JavaScript tools | Exact `package.json` versions plus a committed lockfile with integrity hashes | Dependabot `bun`/`npm` |
| GitHub Actions and reusable workflows | Full 40-character commit SHA with a version comment; same repository as `$/...` | Dependabot `github-actions` |
| pre-commit hook repositories | Full commit SHA with `# frozen: vX` (`pre-commit autoupdate --freeze`) | Dependabot `pre-commit` |
| Toolchains bootstrapped by hooks | Exact `language_version` (for example Go for `actionlint`) | Manual review |
| Container images and Dockerfiles | `image:tag@sha256:<digest>` | Dependabot `docker` |
| Dev container features | `devcontainer-lock.json` with digest and integrity; exact `version` options | Dependabot `devcontainers` |
| CI tool installers | Exact `version:` inputs (uv, Bun, downloaded CLIs), never `latest` | Dependabot or manual |
| MCP stdio servers | `package@x.y.z` or an image digest; remote servers over HTTPS | Manual review |

Published library dependencies are the one deliberate range: exact pins in
package metadata force conflicts on consumers and block their security updates.
Pin the project's own environment through its lockfile instead.

## Commands

- Install only from locks: `uv sync --locked`, `bun install --frozen-lockfile`,
  `npm ci`. Run tools from the locked environment, never through `npx`, `uvx`,
  `bunx` or `pipx`, which resolve versions at run time.
- Never pipe a downloaded script into a shell; download a pinned release and verify
  its checksum or signature.

## Enforcement

Run [check_pins.py](../assets/check_pins.py) from the repository root:

```text
python check_pins.py --root .
python check_pins.py --self-test
```

It reads `pyproject.toml`, `tox.ini`, `.pre-commit-config.yaml`, `package.json`,
Dockerfiles, dev container files, workflows, local actions, `Taskfile.yml` and MCP
manifests. Wire it into the verification gate and an always-running pre-commit
hook, and add negative tests for each rule the repository depends on.

## Limits

- It checks literal references; it cannot see versions computed in scripts.
- An exact version without a hash can still be replaced by a compromised index;
  prefer hashed lockfiles and digests.
- Pins go stale. Pair every pinned surface with an updater and a vulnerability
  audit, or the pin becomes long-lived exposure.

## Sources

- [Security hardening for GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use)
- [Dependabot options reference](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference)
- [pre-commit autoupdate --freeze](https://pre-commit.com/#pre-commit-autoupdate)
- [uv settings](https://docs.astral.sh/uv/reference/settings/)
- [Bun lockfile](https://bun.sh/docs/install/lockfile)
- [Dev container lockfiles](https://containers.dev/implementors/spec/#lock-file)
- [OpenSSF Scorecard Pinned-Dependencies](https://github.com/ossf/scorecard/blob/main/docs/checks.md#pinned-dependencies)
