# Compatibility

## Contract

| Surface | Current evidence |
| --- | --- |
| APM CLI 0.33.0 | Pinned distribution; real install/compile smoke gate |
| Copilot and Claude source-package delivery | Smoke installs selected source-package closures, compiles both targets and replays the lock; published-profile dependency resolution is not tested |
| Repository-owned Copilot and Claude roles | Native source projections and synthetic metadata/selection tests |
| Consumer native agent roles | Not included in generated APM profile packages |
| Native IDE/model/cloud sessions | Not certified by file or APM smoke tests |
| Other agent runtimes | Not selected or claimed supported |
| User-global installation | Not performed automatically |
| Agent Kit command-line interface | Retired; consumer installs use Microsoft's `apm` command |

The source primitive format is portable; interpretation is not universally portable.
Tools, models, permissions, hook events, MCP transports, and discovery need
separate certification for each exact host/version.

The catalog-driven profile generator writes only contained, ledger-owned files.
It refuses links, unowned outputs and independent edits before refreshing
generated packages. Consumer installation is performed by pinned APM.

The optional maintainer source-archive builder still uses the atomic output
adapter: it supports Windows and modern Linux with `renameat2`; other platforms
fail explicitly rather than falling back to overwrite-prone publication.
Windows publication tolerates short-lived access/sharing denials with four
bounded delays totaling 1.5 seconds. Every attempt retains atomic no-replace
rename, rejects an existing destination and rechecks symlink/junction paths.
Persistent denials and unrelated permission errors remain explicit failures.

Planned output components must be safe Windows regular-file names on every
platform. Trailing dots/spaces, reserved device names, alternate-stream colons,
and disallowed/control characters fail before staging writes. This intentionally
rejects names that a Unix filesystem might otherwise permit: composition must
not silently rename files or produce an archive that cannot be relocated.

Maintainer APM checks use the launcher recorded by the pinned distribution in
the active Python environment's scripts directory, not an unrelated executable
on `PATH`. Installations without that recorded executable fail explicitly.
Command timeout values must be finite and positive; NaN and infinity are invalid
configuration.

### Smoke process boundaries

`task apm:smoke` gives each APM command a 120-second deadline, including
policy status, compilation, audit and frozen replay. Override it explicitly
with `-- --timeout-seconds N` (positive integer). Commands announce their
deadline and elapsed time; vendor stdout/stderr stream directly instead of
remaining hidden in captured pipes. Standard input is closed.
Timeouts and interrupts terminate the command's process tree, not just the
Windows launcher. Windows process-tree cleanup and launcher reaping each have
a separate 30-second bound; process creation itself is subject to OS delays.

Disposable workspaces live beneath `build/`, with isolated home, cache and
trust state. A Git discovery ceiling prevents them from inheriting this
checkout's remote: otherwise APM's automatic organization-policy discovery can
probe `gh auth token` and remote policy repositories even for a dependency-free
fixture. Explicit local policy status and audit checks remain mandatory;
no policy, integrity, trust or provenance check is disabled.

See Python's [subprocess timeout contract](https://docs.python.org/3/library/subprocess.html)
and APM's [governance discovery contract](https://microsoft.github.io/apm/enterprise/governance-guide/).
Slow environment startup can still exhaust a deadline; that is a reported
failure, never a passing runtime certification.

### Legacy deployment-ledger limitation

APM 0.33.0 can retain a legacy local deployment row for an already-renamed
resource. In this checkout, reinstalling both targets leaves the missing
`.agents/skills/kit-config-review/references/harness-evaluation.md` recorded even
though the canonical resource is `configuration-evaluation.md`.
The explicit audit fails `deployed-files-present`; this is not source drift.
Do not recreate the obsolete resource or manually edit the lockfile to hide it.
The supported [prune workflow](https://microsoft.github.io/apm/reference/cli/prune/)
repairs orphan packages and invalid owners, not a missing file whose local
owner remains valid. An upstream-supported repair is required if reinstall and
prune leave this record unchanged; retain the failing audit as evidence.

## Native exceptions

- Roles use one procedure body with separately rendered native metadata, flat in
  `.github/agents` and `.claude/agents`.
- There is no shell-less tier: verifiers (analysis, review and checks) get only
  read/search plus a shell for offline inspection, without edit or delegation;
  implementers receive explicit bounded capabilities and
  coordinators use available worker IDs only.
- Copilot visibility/delegation flags (`user-invocable`, `disable-model-invocation`,
  `agents`) have no claimed Claude equivalent and are unsupported on the github.com
  cloud agent.
- Claude `Agent(...)` limits apply when selected as the main agent, not as a worker.
- Model availability depends on the actual provider and account. Configured small
  worker choices are a preference, not proof every host supports them.
- Claude's import is retained for backward-compatible policy discovery.
- VS Code Local disables Claude hook parsing to avoid double execution.
- Agent Host follows its harness; Local workspace settings do not override it.
- The session hook only checks the existence of context entry files and reports
  missing files. It never denies ordinary editing or claims to filter shell commands.

Repository projection ownership requires canonical, runtime-specific role paths
and attested hashes. Existing unowned files are never adopted, even with identical
bytes. The drift check inventories root and nested roles under this repository's
`.github/agents` and `.claude/agents`;
any nested file is reported as unexpected because neither runtime discovery nor
the renderer uses subfolders. It reports unknown roles without deleting them or
scanning user-global discovery.
Session hooks use `--no-sync`; provision their locked environment with the audited
`task bootstrap` workflow before session entry.

Source and CLI tests do not prove native approvals, sandboxing, or cloud behavior.
Before production rollout, exercise actual hosts with synthetic repositories,
record versions and results, and test both allowed and denied operations.

## Package boundaries

The profile generator emits one compact APM meta-package manifest per portable
catalog profile. Each manifest pins the selected source-package closure, without
copying capability files. APM 0.33.0 supports recursive dependency resolution,
but this repository's smoke test installs source packages directly; it does not
certify consumer installation of a published profile tag. The generated-file
ledger detects local manifest drift and is not a substitute for the consumer's
APM lock. Native role files are rendered for this repository from
toolkit-authored role metadata; they are not included in consumer profile
packages.

Composed manifests exclude `.apm/skills`, `.agents/skills` and `.claude/skills`
from compilation's application-placement scan. APM 0.33.0 installation still
delivers the selected skills and resources. This prevents the optimizer from
treating on-demand templates as application files and generating nested always-on
context inside skill assets. Source, installed bytes and both native rosters are
checked before and after frozen installation; no command timeout is increased.

The catalog composer remains an internal maintainer service for validating and
generating profile packages and this repository's native projections. There is no
consumer-facing Agent Kit compose or session-selection command. Consumers select
the smallest profile in `apm.yml`; this does not hide pre-existing
parent/user/plugin capabilities or disable host tools.

The optional `task capabilities:build` target creates a maintainer source
archive; it is not the consumer installation path, a native plugin, or a
dependency-resolved APM bundle. Consumers install the generated profile
directory through APM, which then resolves the pinned source-package closure.

## Integrations and application checks

The root workspace manifests select three reviewed remote services. The shared
editor resource retains inactive examples for the full integration inventory;
portable APM defaults remain deny-by-default. Authentication and host approval
remain user-controlled. None are started by profile generation, resource checks or APM
smoke. Configuration location and host discovery remain version-dependent. No
Windows process sandbox is claimed, and command-hook permissions are not tool
approval rules. See the [MCP adoption record](mcp-adoption.md).
Application DI/port/migration/license checks are not replaced by passing toolkit
checks. See [exclusions and disposition](capability-review.md#exclusions-and-disposition).
