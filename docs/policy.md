# APM policy

[apm-policy.yml](../apm-policy.yml) is an explicit, strict baseline:

- No dependency packages are allowed. The root workspace permits only the
  three reviewed MCP names listed in the policy; consumer templates start empty.
- Lifecycle scripts and dependency executables are denied.
- Explicit manifest includes, integrity hashes, and drift failures are required.
- Unknown policy keys are rejected by the toolkit, including nested keys.

## Enforcement

```powershell
uv run agent-kit check --root .
uv run agent-kit provenance --root build/backend
uv run apm policy status --policy-source ./apm-policy.yml --check --json
```

Run APM policy commands from the package being inspected.
After native installation, run the explicit audit through `agent-kit apm-check`.

**APM 0.33.0 does not automatically select every project-local policy file during
installation.** A checked-in filename is not an install-time enforcement boundary.
The supported compose path validates policy before it creates a package.
Direct APM invocation can bypass that wrapper; CI must require its checks.

`version` is a policy revision, not a minimum CLI version. The exact CLI version
is pinned in the Python manifest and lock, then checked at the executable boundary.

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
- To enable a dependency later, declare its exact approved source and release,
  review executables, add allow-list entries, and retain a negative policy test.

## What the policy does not do

`apm-policy.yml` governs package sources, primitive trust, manifest contents,
integrity and auditing. It is not a Git-command permission file. For example:

```yaml
dependencies:
  allow: []
manifest:
  scripts: deny
executables:
  deny_all: true
```

In the full policy, these sections mean "accept no dependency packages or
package lifecycle scripts/executables." They do not mean "deny `git add`."
Conversely, placing a Python checker in a skill's `assets/` distributes source
without registering it as a native executable hook.

The pinned APM 0.33 executable policy supports package-level `deny_all`, `deny`,
`require`, `recommend` and `enforce` fields. `enforce` degrades to recommendation
in that version; none is a per-file SHA-256 allowlist. An ancestor's
`deny_all: true` cannot be bypassed by adding a recommendation in a child.
Do not invent an `allow`/`hashes` field or set `deny_all: false` to imply
only one safe executable is enabled.

The existing runtime skill supplies a separate
[read-only Git policy](../packages/shared/.apm/skills/kit-agent-runtime/assets/git_readonly_policy.json.template)
and documents its [scope and bypasses](../packages/shared/.apm/skills/kit-agent-runtime/references/guards.md#read-only-git-for-consumer-sessions).
It is inactive until a reviewed native handler is registered. Automatic package
hook delivery, an APM approval handshake and the kit-maintenance exception need
actual host and pinned-CLI verification before enabling them.

Sources: [APM governance](https://microsoft.github.io/apm/consumer/governance-on-the-consumer-ramp/)
and [Claude hooks](https://code.claude.com/docs/en/hooks). Installed APM policy
source was inspected for the field descriptions above and compared with current
official documentation. Native host activation remains a separate verification.
