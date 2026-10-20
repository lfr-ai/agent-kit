# APM policy

[apm-policy.yml](../apm-policy.yml) is an explicit, strict baseline:

- No dependency packages or MCP services are allowed by default.
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
- Native hooks/permissions and pre-existing MCP servers are outside this policy.
- The session-entry hook is advisory and grants no authorization.
- There is no bundled shell-filter security boundary. Enforce restrictions through
  native approval modes, least-privilege identities, and managed controls.
- Never use force, strip, disabled policy, or weakened hashes to make a gate pass.
- To enable a dependency later, declare its exact approved source and release,
  review executables, add allow-list entries, and retain a negative policy test.
