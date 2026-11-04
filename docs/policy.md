# APM policy

[apm-policy.yml](../apm-policy.yml) is an explicit, strict baseline:

- The source-repository baseline allows no package dependencies. Consumer
  policies must separately allow the selected profile and its pinned Agent Kit
  source-package dependencies.
- MCP servers are limited to the reviewed names in the policy. They are declared
  in place (`self_defined: allow`) over `http` or `stdio` only, and never from the registry.
  The inventory and the way the allow list stays in step with every package
  manifest are in [MCP adoption](mcp-adoption.md#policy-alignment).
- Lifecycle scripts are denied. Hooks are delivered only as the reviewed Git guard.
- Explicit manifest includes, integrity hashes, and drift failures are required.
- Unknown policy keys are rejected by the toolkit, including nested keys.

## Enforcement

```powershell
task verify -- source
task verify -- profiles
uv run apm policy status --policy-source ./apm-policy.yml --check --json
```

Run APM policy commands from the repository being inspected. Consumers use
`apm audit --ci --policy ./apm-policy.yml` after installation; no Agent Kit
wrapper is required.

**APM 0.33.0 does not automatically select every project-local policy file during
installation.** A checked-in filename is not an install-time enforcement boundary.
The profile source checks validate Agent Kit's canonical packages, but they do
not wrap or authorize a consumer's direct APM invocation. Consumers must require
policy and audit checks in CI; organization-managed policy is the install-time
enforcement boundary where available.

`version` is a policy revision, not a minimum CLI version. The exact CLI version
is pinned in the Python manifest and lock, then checked at the executable boundary.
APM 0.35.0 was the latest release on 2026-11-04; this repository still pins
0.33.0 until the documented 14-day cooldown ends on 2026-11-05
([upgrade evidence](sources.md#pins)). Between these versions, frozen
installation no longer rewrites an incomplete lock and instead fails with the
unrecorded paths. Version 0.35.0 also verifies local snapshots against locked
hashes in frozen mode and fails closed when an explicitly supplied policy cannot
be loaded. Reassess after the cooldown; before changing the pin, test the
current lock against frozen install and rerun the APM smoke. Change the pin only
through the reviewed dependency workflow.
Every policy key this repository uses is valid in APM policy; APM also
supports `unmanaged_files`, `executables` and `compilation` sections that this
baseline does not set.

## Scope

- `APM_NO_SCRIPTS=1` is required for the controlled APM process.
- Root first-party content is trusted by APM; review it as executable context.
- Native host authorization remains separate from this policy. Its MCP
  allowlist checks server identities, not endpoint equivalence, authentication,
  or effective tool permissions.
- The session-entry hook is advisory and grants no authorization.
- There is no bundled shell-filter security boundary. Enforce restrictions through
  native approval modes, least-privilege identities, and managed controls.
- Never use force, strip, disabled policy, or weakened hashes to make a gate pass.
- Generated profile meta-packages resolve pinned source-package dependencies.
  Their own manifest declares the selected MCP servers directly, so consumer
  policy can keep `mcp.trust_transitive: false`.
- Consumer policies should allow only the Agent Kit profile and source-package
  paths needed by the selected profile, plus its reviewed MCP names. Keep the
  consumer lockfile under review; the source-repository policy is not inherited.

## What the policy does not do

`apm-policy.yml` governs package sources, primitive trust, manifest contents,
integrity and auditing. It is not a Git-command permission file. For example:

```yaml
dependencies:
  allow: []
manifest:
  scripts: deny
```

In the source-repository policy these sections mean "accept no dependency
packages or lifecycle scripts." A consumer configures its own dependency
allowlist for Agent Kit profile packages and their source dependencies. These
sections do not mean "deny `git add`." The Git rules live in the delivered hook
policy below.

APM 0.33 has no per-file SHA-256 allowlist for executables, and its
`executables.deny_all` would also park the hook and MCP servers this kit delivers,
so the policy omits it. Executable content is constrained by the closed schemas
that the repository's `task verify -- source` gate enforces (see below), not by
a consumer-facing Agent Kit command.

## Delivered hooks and MCP servers

Hooks and MCP are delivered by APM, not copied by hand:

- **Hook.** `shared` ships one `preToolUse` hook, [git-guard.json](../packages/shared/.apm/hooks/git-guard.json),
  which runs the [guard](../packages/shared/.apm/hooks/scripts/tool_guard.py) with
  [git-guard.policy](../packages/shared/.apm/hooks/scripts/git-guard.policy).
  APM merges it into `.github/hooks/` and `.claude/settings.json`. Every profile includes `shared`.
- **MCP.** Each profile manifest declares the selected `dependencies.mcp`;
  APM writes `.mcp.json` and `.github/mcp.json`.
- **Closed schemas.** `task verify -- source` rejects any hook or server outside the
  schema in [executables.py](../src/agent_kit/core/executables.py): hooks run only a
  bundled `python ./scripts/<name>.py`; servers are `https` or loopback `http`
  without credentials, `bunx --bun pkg@x.y.z`, or `docker run -i --rm image@sha256:...`;
  names must appear in the policy allow list.
- **Git scope.** Outside the registered kit checkout, Git is read-only. Inside it,
  staging, commits, switch, restore, fetch, pull and an explicit
  `git push origin feature/example` pass to native authorization. Force pushes,
  known default names (`main`, `master`, `trunk`, `HEAD`), implicit targets,
  refspecs, tags and hook bypass stay denied. Check the actual remote default
  branch separately. Configuration never authorizes a push in a session by itself.
- **Safety rules.** The same hook also denies credential-file access, recursive
  deletion, disk formatting, downloaded/encoded script execution, TLS bypass,
  privilege escalation, environment dumps, database mutations and unaudited
  installers. See the [rule reference](../packages/shared/.apm/skills/kit-agent-runtime/references/guards.md).
  Database inspection still needs a read-only identity; regex matching is not a
  SQL parser. Installation is operator-only: this hook cannot prove an audit ran.
- **Requirements.** Python 3.13 as `python3` (macOS, Linux, Copilot cloud agent)
  or `python` (Windows). The registration names both a `bash` and a `powershell`
  command because Copilot hosts read the key for their shell; the cloud agent
  runs Linux and honors only `bash`.
- **Paths.** The commands use `./scripts/<name>.py`, relative to the hook file.
  APM rewrites that to the deployed hook directory for each host
  (`.github/hooks/scripts/<package>/` for Copilot) and to
  `${CLAUDE_PROJECT_DIR}/.claude/hooks/<package>/` for Claude Code, so a
  command never depends on the session's working directory. The policy file
  sits beside the launcher, which passes it to the engine, and JSON assets are
  avoided in the script directory because Copilot's hook loader rejects JSON
  files without a `hooks` key.
- **Failure semantics.** Copilot treats a command `preToolUse` hook that crashes
  or exits non-zero as a denial, but a timeout is always fail-open, so the
  registration sets an explicit `timeoutSec` of 10 (the host default is 30) and
  the schema caps it at 30. Claude Code blocks only on exit code 2; any other
  failing status, including a Python traceback (exit 1) or a missing
  interpreter, is a non-blocking error. The launcher and engine therefore
  return 2 for every unreadable payload, invalid policy, or engine that cannot be loaded.
  Claude Code 2.1.295 and later also accept `"onFailure": "block"` on a command
  hook, which would cover a missing interpreter too; the closed schema in
  `executables.py` does not accept that field yet, so adding it is a reviewed
  schema change.
- **Approval.** To require review before executables land, add an
  `executables: {allow: {}}` block to the consumer `apm.yml`, then run
  `apm approve <package>` (`--user` for user scope).
- **Pins.** Dependabot cannot bump `apm.yml` pins. Review MCP versions manually.

A hook is not a sandbox: it sees only the literal tool input, and a capable agent
can evade it through indirection (variables, generated scripts, interpreters,
encoded payloads, symbolic links) or through a tool the policy does not name.
It never approves a call; an unmatched call keeps the host's normal permission
flow. Keep native approvals, least-privilege identities and branch protection.
Hooks for Git itself (pre-commit, commit-msg, pre-push) are a different layer
that runs on the developer's machine and can be skipped with `--no-verify`; see
the `kit-git-hooks` skill, and keep CI as the enforcement boundary.

Minimal kit example (inspection only; no command is run by this documentation):

```powershell
$env:AGENT_KIT_DIR = (Get-Location).Path
git fetch origin
git pull --ff-only
# Only after approving this exact command in the agent session:
git push origin feature/example
```

The scope must be an existing absolute directory. Symlinks are resolved before
containment checks; missing/relative scopes never grant an exception. When
installing virtual packages directly, include `shared` alongside each optional
package. For a profile, reference its generated APM manifest; it declares the
selected source-package closure.

Sources: [APM governance](https://microsoft.github.io/apm/consumer/governance-on-the-consumer-ramp/),
[APM hooks and commands](https://microsoft.github.io/apm/producer/author-primitives/hooks-and-commands/),
[Copilot hooks](https://docs.github.com/en/copilot/reference/hooks-configuration)
and [Claude hooks](https://code.claude.com/docs/en/hooks). Delivery was verified
with APM 0.33.0 in disposable folders; native host activation remains a separate check.
