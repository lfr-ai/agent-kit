# Locking, pinning, auditing and updates

Review date: 2026-11-02.

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

`uv export --format requirements.txt` writes hashes by default. Use it only for
tools that need a requirements file, for example `pip-audit --require-hashes`
in a project that is not uv-managed; uv projects audit `uv.lock` directly with
`uv audit`.

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
3. Audit the lock without installing the project, then install from it:
   - Python with uv: `uv audit --locked --preview-features audit-command`.
     `uv audit` is a preview command; the flag silences the warning. It reads
     `uv.lock`, queries OSV only, audits all groups and extras by default
     (`--no-dev`, `--no-group`, `--only-group` narrow it) and needs network
     access. It exits 1 on a vulnerability. Adverse project statuses
     (PEP 792 archived, deprecated, quarantined; reported since uv 0.11.9) do
     not change the exit code, so gate on the JSON report:
     `uv audit --locked --preview-features audit-command,json-output --output-format json`
     (JSON needs uv 0.11.15 or later) and fail when `summary.vulnerabilities`
     or `summary.adverse_statuses` is nonzero. `--output-format sarif` is also
     available; check `uv audit --help` for the installed release.
     `--service-url` with `--service-format osv` points at an OSV-protocol
     mirror.
   - Hash-integrity limitation: `uv audit` does not compare lock hashes with
     the index. Compensate with `uv sync --locked`, which verifies each
     artifact hash at install, review of lock diffs, and the dependency-review
     action on pull requests.
   - Python without uv (requirements files): `pip-audit --requirement req.txt
     --require-hashes --disable-pip --strict`; export hashes with
     `uv export --locked --all-groups --no-emit-project --format requirements.txt --output-file req.txt`
     only when a uv project must feed such a tool.
   - Multi-ecosystem or any lockfile OSV-Scanner understands:
     `osv-scanner scan source --lockfile uv.lock` (also `package-lock.json`,
     `bun.lock` and others); `--format sarif` for code scanning upload.
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
date; add the narrowest ignore and remove it when a fix ships. With uv use
`uv audit --ignore-until-fixed <ID>`: it suppresses the advisory (aliases
included) only while no fix version exists and reports it again once one does;
plain `--ignore <ID>` never expires, so reserve it for a documented
not-affected decision. Every ignore carries a comment or config note naming the
tracked issue, owner and expiry; an ignore without a tracked issue is rejected.
Other tools: `pip-audit --ignore-vuln <ID>`, or an OSV-Scanner config entry
with `ignoreUntil` and a reason.

## Failure modes

- **Hashes stripped on export.** In a requirements-file audit, `--no-hashes` or
  a file without hashes lets a tampered artifact install. That audit command
  fails closed with `--require-hashes`.
- **Adverse statuses ignored.** `uv audit` exits 0 for an archived, deprecated
  or quarantined project; without the JSON `summary.adverse_statuses` check
  they pass silently.
- **Audit mistaken for integrity proof.** `uv audit` checks advisories, not
  lock hashes; install with `uv sync --locked` and review lock diffs.
- **Preview drift.** `uv audit` is a preview feature; pin uv, keep the
  `--preview-features` flags explicit and re-check `uv audit --help` on upgrade.
- **Lock regenerated with unrelated upgrades.** Use
  `uv lock --upgrade-package <name>`, not a blanket `--upgrade`, in a
  single-purpose change.
- **Source-only package.** A package without wheels builds on install; it
  either gets reviewed or replaced.
- **Audit tool installed unpinned.** The auditor is part of the supply chain;
  lock it like any other tool.

## Primary sources

Reviewed 2026-11-02.

- uv, [Locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- uv, [Exporting a lockfile](https://docs.astral.sh/uv/concepts/projects/export/)
- uv, [CLI reference: `uv audit`](https://docs.astral.sh/uv/reference/cli/#uv-audit) and [preview features](https://docs.astral.sh/uv/concepts/preview/)
- uv, [Release notes](https://github.com/astral-sh/uv/releases)
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
