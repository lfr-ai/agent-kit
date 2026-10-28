# Compatibility

## Contract

| Surface | Current evidence |
| --- | --- |
| APM CLI 0.33.0 | Pinned distribution; real install/compile smoke gate |
| Copilot files | Native source projections and synthetic metadata/selection tests |
| Claude files | Native source projections and synthetic metadata/selection tests |
| Native IDE/model/cloud sessions | Not certified by the CLI smoke gate |
| Other agent runtimes | Not selected or claimed supported |
| User-global installation | Not performed automatically |

The source primitive format is portable; interpretation is not universally portable.
Tools, models, permissions, hook events, MCP transports, and discovery need
separate certification for each exact host/version.

Composition supports Windows and modern Linux with renameat2. Other platforms
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

APM commands use the launcher recorded by the pinned distribution in the active
Python environment's scripts directory, not an unrelated executable on `PATH`.
Installations without that recorded executable fail explicitly. Command timeout
values must be finite and positive; NaN and infinity are invalid configuration.

## Native exceptions

- Roles use one procedure body with separately rendered native metadata.
- Read-only workers omit shell/edit/delegation; implementers receive explicit
  bounded capabilities and coordinators use available worker IDs only.
- Copilot visibility/delegation flags have no claimed Claude equivalent.
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
`.github/agents` and `.claude/agents`, except the two root `kit-reviewer` definitions;
it reports unknown roles without deleting them or scanning user-global discovery.
Session hooks use `--no-sync`; provision their locked environment with the audited
`task bootstrap` workflow before session entry.

Source and CLI tests do not prove native approvals, sandboxing, or cloud behavior.
Before production rollout, exercise actual hosts with synthetic repositories,
record versions and results, and test both allowed and denied operations.

## Package boundaries

Compose selects only approved bundles into a clean source root before APM runs.
This avoids recursive compilation discovering dormant sibling packages.
The package contains first-party primitives and no local-path dependencies;
its provenance is not a substitute for pinning the released toolkit revision.
Native role files are toolkit-authored projections included in source provenance,
not APM's verbatim cross-provider agent conversion.

Composed manifests exclude `.apm/skills`, `.agents/skills` and `.claude/skills`
from compilation's application-placement scan. APM 0.33.0 installation still
delivers the selected skills and resources. This prevents the optimizer from
treating on-demand templates as application files and generating nested always-on
context inside skill assets. Source, installed bytes and both native rosters are
checked before and after frozen installation; no command timeout is increased.

`compose --skill` narrows procedures inside the chosen profile, without projecting
native role files. Selected skill assets remain original, including any role JSON;
resource JSON is not an active agent definition. Project instructions and policy
remain unchanged. This does not hide pre-existing parent/user/plugin capabilities
or disable host tools; native task selection and tool approval remain necessary.

`task capabilities:build` archives the selected first-party APM source layout.
Extract it before installation. It is not a native plugin or a dependency-resolved
APM bundle. In the tested release, legacy `apm pack --format apm` emitted an empty
archive for this root-only package; the toolkit checks source archive contents
instead of treating that zero exit status as a successful distribution.

## Integrations and application checks

The root workspace manifests select three reviewed remote services. The shared
editor resource retains inactive examples for the full integration inventory;
portable APM defaults remain deny-by-default. Authentication and host approval
remain user-controlled. None are started by composition, resource checks or APM
smoke. Configuration location and host discovery remain version-dependent. No
Windows process sandbox is claimed, and command-hook permissions are not tool
approval rules. See the [MCP adoption record](mcp-adoption.md).
Application DI/port/migration/license checks are not replaced by passing toolkit
checks. See the explicit [setup review](setup-review.md).
