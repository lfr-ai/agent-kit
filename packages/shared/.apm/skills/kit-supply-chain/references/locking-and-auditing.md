# Locking, pinning, auditing and updates

Review date: 2026-10-23.

## Lockfiles and hashes

A lockfile records the full resolved graph with an integrity hash for each
artifact, so the same input installs the same bytes everywhere. Commit it, and
install from it with a flag that fails instead of re-resolving.

| Ecosystem | Lockfile | Integrity | Install without re-resolving | Freshness check |
| --- | --- | --- | --- | --- |
| Python with uv | `uv.lock` | `sha256` per wheel and sdist | `uv sync --locked` | `uv lock --check`; [lock freshness checker](../assets/check_lock_freshness.py) |
| Python with pip | `requirements.txt` with `--hash` lines (compiled or exported) | `--require-hashes` | `pip install --require-hashes -r requirements.txt` | regenerate and diff |
| npm | `package-lock.json` | `integrity` (SHA-512) | `npm ci` | `npm ci` fails on mismatch |
| Bun | `bun.lock` | `integrity` per package | `bun install --frozen-lockfile` | same command |

`uv export --format requirements.txt` writes hashes by default, which lets
`pip-audit --require-hashes` audit exactly what is locked.

## Exact pins or ranges

| Artifact | Manifest constraint | Lock | Why |
| --- | --- | --- | --- |
| Application, service, internal tool | any reasonable range or exact pin | exact versions with hashes, committed | deployments must be reproducible |
| Library published to an index | lower bound plus an upper bound below the next breaking major when the upstream follows semantic versioning | lock the tested build for CI only | exact pins in metadata cause conflicts for consumers and block their security fixes |
| Development and CI tools (linters, test runners, audit tools) | `==` in a dependency group | hashed | tool output must not change between runs |
| Build backend | `==` in `build-system.requires`, with a constraint list for its closure where supported | via build constraints | the build itself executes this code |
| Interpreter | minor version range | runner or image pin | patch releases carry security fixes |

The lock freshness checker reports an `==` pin that disagrees with the locked
version, a lock that no longer matches the declared requirements, and any
registry or URL package without a hash. Floating versions in workflows, hooks,
images and package-runner commands are the pin checker's job (`check_pins.py`,
owned by `kit-verify-change`); run both.

## Audit before install

1. Change the manifest and lock without installing (`uv add --no-sync`,
   `uv lock`, `uv remove --no-sync`).
2. Run the lock freshness checker.
3. Install only the hash-locked audit tool group, then audit the lock:
   - Python: `uv export --locked --all-groups --no-emit-project --format requirements.txt --output-file req.txt`
     then `pip-audit --requirement req.txt --require-hashes --disable-pip --strict`.
   - Any lockfile OSV-Scanner understands: `osv-scanner scan source --lockfile uv.lock`
     (also `package-lock.json`, `bun.lock` and others); `--format sarif` for code
     scanning upload.
   - JavaScript: `bun audit` or `npm audit --audit-level=low`; `npm audit signatures`
     verifies registry signatures and provenance for installed packages.
4. Install from the audited lock (`uv sync --locked`, `npm ci`,
   `bun install --frozen-lockfile`). Use `--no-build` for third-party packages
   where wheels exist.
5. Check installed licenses with the license guard (`kit-agent-runtime`) and
   run the project gate.

Pull-request dependency review evaluates the diff again on the server: fail on
any severity in runtime, development and unknown scopes, and keep its
`allow-licenses` list identical to the license allow-list. Its configuration
lives with the CI templates of `kit-ci-review`. A scheduled audit of the whole
lock catches advisories published after merge.

## License policy

Keep one reviewed allow-list (SPDX identifiers), a deny-list for licenses that
are never acceptable, and per-package exceptions that match the exact observed
metadata and expire. Do not widen the allow-list to accept unknown metadata;
read the bundled license file and add a dated exception. The license guard and
its allow-list template are owned by `kit-agent-runtime`.

## Cooldowns against freshly published releases

Most malicious releases are detected and removed within days. Delaying version
updates gives that detection time to work. Never delay security updates.

| Tool | Setting | Notes |
| --- | --- | --- |
| Dependabot | `cooldown.default-days` (plus `semver-major-days`, `semver-minor-days`, `semver-patch-days`, `include`, `exclude`) | applies to version updates only; security updates are exempt |
| Renovate | `minimumReleaseAge` per rule | set `vulnerabilityAlerts.minimumReleaseAge` to `null` so fixes are not delayed |
| Bun | `install.minimumReleaseAge` in `bunfig.toml` or `--minimum-release-age` | applies to resolution on install and update |
| uv | `exclude-newer` (date or duration) | a global cut-off also blocks same-week security fixes; use it per manual update, for example `uv lock --upgrade-package <name> --exclude-newer "14 days"` |
| zizmor | `dependabot-cooldown` rule | fails a Dependabot file whose cooldown is missing or shorter than the configured minimum |

A cooldown of 7 to 14 days is common. Cooldown controls release age, not the
update schedule; a weekly schedule may propose an update later than the
cooldown alone would.

## Vulnerability exceptions

When no fixed version exists: record the advisory identifier, the affected
code path and whether it is reachable, a tracked issue, an owner and an expiry
date; add the narrowest ignore (`pip-audit --ignore-vuln <ID>`, an OSV-Scanner
config entry with `ignoreUntil` and a reason) and remove it when a fix ships.

## Failure modes

- **Hashes stripped on export.** `--no-hashes` or a requirements file without hashes
  lets a tampered artifact install. The audit command fails closed with
  `--require-hashes`.
- **Lock regenerated with unrelated upgrades.** Use
  `uv lock --upgrade-package <name>`, not a blanket `--upgrade`, in a
  single-purpose change.
- **Source-only package.** A package without wheels builds on install; it
  either gets reviewed or replaced.
- **Audit tool installed unpinned.** The auditor is part of the supply chain;
  lock it like any other tool.

## Primary sources

Reviewed 2026-10-23.

- uv, [Locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- uv, [Exporting a lockfile](https://docs.astral.sh/uv/concepts/projects/export/)
- uv, [Settings: `exclude-newer`, `no-build`](https://docs.astral.sh/uv/reference/settings/)
- PyPA, [Dependency groups specification](https://packaging.python.org/en/latest/specifications/dependency-groups/)
- PyPA, [Secure installs with pip](https://pip.pypa.io/en/stable/topics/secure-installs/)
- PyPA, [pip-audit](https://github.com/pypa/pip-audit)
- Google, [OSV-Scanner](https://google.github.io/osv-scanner/)
- npm, [npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci) and [npm audit](https://docs.npmjs.com/cli/v11/commands/npm-audit)
- Bun, [bun install](https://bun.com/docs/pm/cli/install) and [bun audit](https://bun.com/docs/pm/cli/audit)
- GitHub, [Dependabot options reference](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference)
- Renovate, [Minimum release age](https://docs.renovatebot.com/key-concepts/minimum-release-age/)
- zizmor, [Audit rules](https://docs.zizmor.sh/audits/)
