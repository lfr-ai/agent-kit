# Compatibility

## Contract

| Surface | Current evidence |
| --- | --- |
| APM CLI 0.35.0 | Pinned distribution; real install/compile smoke gates |
| Copilot and Claude source-package delivery | Four composed selections passed installation, compilation, audit and frozen provenance/resource checks with an explicit 300-second command deadline |
| Repository-owned Copilot and Claude roles | Native source projections and synthetic metadata/selection tests |
| Consumer native agent roles | Released-APM installation, exact roster comparison, audits and frozen replay passed for all three target selections with an explicit 300-second command deadline |
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

Source-smoke workspaces live beneath `build/`, with isolated home, cache and
trust state. A Git discovery ceiling prevents them from inheriting this
checkout's remote: otherwise APM's automatic organization-policy discovery can
probe `gh auth token` and remote policy repositories even for a dependency-free
fixture. Explicit local policy status and audit checks remain mandatory;
no policy, integrity, trust or provenance check is disabled.

`task apm:smoke` first tests native profile dependency resolution, then the
composed source selections. `task apm:smoke -- --native` runs only the bounded
native proof. It copies unchanged generated packages into a
disposable catalog, relocates the fixture, and uses APM 0.35.0 root `replace`
rules for the pinned profile and its transitive dependencies. APM alone installs
the native files; the consumer starts without role files. The check compares
actual filenames, full provider metadata and bodies to the shared renderer,
rejects unselected-target output, audits both installs and requires frozen replay
to preserve the lock. This tests local resolution of the generated `shared`
profile, not fetching an unpublished release tag or every profile's entire closure.
All portable profiles' native dependency references are covered structurally.
Native fixtures use short system-temporary paths because APM replacement
staging can exceed Windows path limits beneath a deep checkout. Their home,
cache, trust state and Git discovery remain isolated in the temporary fixture.
The default Windows run installed and compiled Copilot's 18 roles and passed
audit, then timed out during frozen installation at the 120-second deadline.
With the explicit `-- --timeout-seconds 300` override, the native proof passed
Copilot-only, Claude-only and combined selection: exact inventories of 18, 18
and 36 roles, both audits, and unchanged frozen locks. This is functional
evidence under the stated deadline, not a passing result for the default
deadline or native IDE/model execution. The default remains unchanged.

On the 2026-11-11 readiness rerun, frozen Copilot installation timed out even
with the explicit 300-second deadline. That run did not complete the smoke
matrix; the earlier passing evidence above is historical, not a fresh pass.
Installation, compilation and audit output before the timeout do not replace
the missing frozen-replay result.

The 2026-11-12 reruns used the default deadline under concurrent machine load.
Two attempts passed every native selection but timed out in the first combined
source installation. The third passed the full default smoke: 47 commands,
native inventories of 18, 18 and 36 roles, and the fullstack, ai, workflows and
backend source selections. The slowest combined installation took 119.5
seconds, so the default deadline leaves little headroom on a loaded Windows
host. Separate runs also failed with `WinError 5 Access is denied`, in APM's
staged-activation rename and in the native fixture relocation. That matches
[microsoft/apm#3386](https://github.com/microsoft/apm/issues/3386), fixed in
APM 0.35.1. The pin stays at 0.35.0 until the dependency cooldown allows a
reviewed upgrade (`uv add --no-sync`, then `task verify -- dependencies`);
rerun this smoke afterwards. A Windows timeout or access-denied failure is
retried, not suppressed.

APM 0.35.0 creates a local installation identity, separate from source and
deployment ownership. With a valid ledger, provenance accepts only its paired
`.apm-local/.gitignore` (`*` plus newline) and `.apm-local/installation`
(32 lowercase hexadecimal characters plus newline). Invalid pairs, extra
files and links remain errors. The marker never grants ownership or replaces
the deployment audit.

APM 0.35.0 can also record hashes on MCP URI rows during replay. These fingerprint
individual native configuration entries, not filesystem paths. Source provenance
requires project ownership, a declared server, a selected runtime and the exact
canonical JSON hash of its authored projection. Native configuration is checked
separately against that projection. Undeclared or retargeted registrations,
rewritten hashes over changed configuration, and non-JSON declarations remain
errors; no additional runtime or source ownership is inferred.

See Python's [subprocess timeout contract](https://docs.python.org/3/library/subprocess.html)
and APM's [governance discovery contract](https://microsoft.github.io/apm/enterprise/governance-guide/).
Slow environment startup can still exhaust a deadline; that is a reported
failure, never a passing runtime certification.

### Legacy deployment-ledger recovery

APM 0.33.0 retained a legacy local deployment row for an already-renamed
resource; upgrading to 0.35.0 and reinstalling both targets initially left the missing
`.agents/skills/kit-config-review/references/harness-evaluation.md` recorded even
though the canonical resource is `configuration-evaluation.md`.
The explicit audit failed `deployed-files-present`, not source drift.
The supported [prune workflow](https://microsoft.github.io/apm/reference/cli/prune/)
repairs orphan packages and invalid owners, not a missing file whose local
owner remains valid.

The checkout was recovered using only the released APM 0.35.0 CLI:

1. Preserve the failed audit, lockfile and current generated bytes.
2. In a disposable copy, replace only the affected skill's source with its
   authenticated historical version from Git revision
   `513c10154e487f7aeadb2b88d0406d0581afe3e7`.
3. Run `apm install --root <destination> --target copilot,claude --no-trust-bin --audit block`
   from that source copy. APM materializes the real historical resource and
   records concrete target ownership.
4. Run the same command from an unchanged current-source copy. APM now retires
   the obsolete, target-owned resource and its receipt through normal reconciliation.
5. Audit from the destination using `apm audit --ci --policy apm-policy.yml`.
   Compare every original generated file and all authored source bytes.
6. Confirm that deliberately changed output still fails in the disposable copy
   before applying the proven sequence to the checkout.

The checkout audit now passes all 31 checks. Only the obsolete receipt and its
compatibility indexes changed; current generated bytes and authored sources were
preserved. The retired resource is absent from both targets and the lockfile.
No ledger mutation API, hand edit, force, strip or policy bypass was used.
This is a verified recovery for this historical source transition, not a general
repair command. Stop if authentic historical source or equivalent evidence is
unavailable; never fabricate an obsolete resource merely to satisfy an audit.

One local skill update on APM 0.35.0 returned success while reporting an
untrustworthy deployment baseline, then removed the skipped skill's old
generated files during cleanup. A subsequent ordinary installation into the
empty destinations restored the current skill without force or manual edits;
the separate obsolete receipt required the recovery above. Always inspect the installed inventory
and audit after refresh: an installation exit code alone is insufficient.
This observation does not authorize blind retries or ledger repair.

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
- Claude's `@AGENTS.md` import is retained for Claude Code releases that predate
  native AGENTS.md discovery (2.1.277); newer releases read only CLAUDE.md when
  both files exist, so removing the import would drop the shared policy.
- VS Code Local disables Claude hook parsing to avoid double execution.
- Agent Host follows its harness; Local workspace settings do not override it.
- The session hook only checks the existence of context entry files and reports
  missing files. It never denies ordinary editing or claims to filter shell commands.
- The edit feedback hook runs after edit tools and returns findings as context.
  It is advisory: hosts that skip `PostToolUse` lose early feedback, not a gate.

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

## GitHub Copilot CLI

Copilot CLI 1.0.89 was inspected offline in this checkout (`copilot instruction
list`, agent and skill discovery); no model session or approval prompt was
exercised. It uses the same generated files as the IDE adapters:

| Surface | Discovered from | Note |
| --- | --- | --- |
| Repository instructions | `.github/copilot-instructions.md`, `AGENTS.md`, `CLAUDE.md` | Merged without precedence; the CLAUDE.md import loads AGENTS.md twice. |
| Path instructions | `.github/instructions/`, `.claude/rules/` | Both targets load; each rule appears twice. |
| Roles | `.github/agents/`, `.claude/agents/` | `.github/agents` wins by name. |
| Skills | `.agents/skills/`, `.claude/skills/` | First match by name wins; no duplicates. |
| Hooks | `.github/hooks/`, `.claude/settings.json` | Documented as combined, so both advisory hooks may run; not exercised live. |
| MCP servers | `.mcp.json` | Loaded only in a trusted folder and subject to organization policy; `.vscode/mcp.json` is ignored. |

Prompt files are IDE-only. Claude permission rules in `.claude/settings.json`
are not Copilot CLI tool approvals; use `--deny-tool` or user settings for that
host. The duplicated instructions are the accepted cost of
supporting older Claude Code releases and both native targets; they add context,
not conflicting rules, because both copies come from the same source.

## Package boundaries

The profile generator emits one compact APM meta-package manifest per portable
catalog profile and two shared native packages under `profiles/native/`.
Each profile pins its selected source-package closure and both native packages.
Native dependency objects use `git`, `path`, `ref` and `targets` so APM 0.35.0
selects only the provider-specific package for each target; a package's top-level
`targets` declaration alone is not the dependency selection contract.
The packages explicitly include `.apm/agents/`, containing the shared renderer's
18 canonical roles: `kit-orchestrator`, `kit-debug` and all 16 workers.
No custom consumer installer or copied native discovery tree is needed.
The same ledger, containment, collision checks and atomic rollback own profile
manifests and native package files. That ledger is not the consumer's APM lock.

Composed manifests exclude `.apm/skills`, `.agents/skills` and `.claude/skills`
from compilation's application-placement scan. APM installation still
delivers the selected skills and resources. This prevents the optimizer from
treating on-demand templates as application files and generating nested always-on
context inside skill assets. Source, installed bytes and both native rosters are
checked before and after frozen installation. The default command deadline is
unchanged; explicit slow-host overrides are described above.

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
