# Security policy

## Reporting

Do not publish credentials or exploit details in public issues or pull requests.
Use **Security -> Report a vulnerability** on the hosting repository.
If that control is unavailable, use `security_contact` in
[maintainers.json](.github/maintainers.json).

The private contact is [lfr@tik-ai.dk](mailto:lfr@tik-ai.dk). Prefer GitHub
private vulnerability reporting and use email only when it is unavailable.

Include a synthetic reproduction, affected version, impact, and proposed fix
where available. Maintainers coordinate a private patch and advisory before
public details. There is no guaranteed response SLA or paid bounty.

## Supported versions

Only the current released 0.1.x line is eligible for security fixes.
This is an early-adoption toolkit, not a declaration of live-runtime certification.
Use pinned versions; a newer unsupported line or a moving branch is not implicitly covered.

## Boundaries

- The advisory session hook is not authorization or a sandbox.
- APM package integrity is not a malware verdict.
- The supported compose path rejects weakened/unknown policy and unsafe paths.
- Native permissions, credentials, and managed policy remain host-specific.
- Never expose CI secrets to fork-triggered workflows.
- Keep releases pinned and auditable; review script and integration changes as code.
- Dependencies change only through the reviewed, audited lockfile; see
  [dependency security](docs/dependency-security.md) for vulnerability, license,
  and agent-install controls and their limits.

## Maintainer handling

1. Confirm the report privately without requesting production secrets.
2. Reproduce with synthetic inputs and assess affected releases.
3. Add a regression, prepare the patch, and coordinate disclosure.
4. Publish a reviewed release and advisory; provide upgrade or mitigation guidance.
