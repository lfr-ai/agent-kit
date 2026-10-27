# Remote access review guide

Reviewed 2026-10-23 against OpenSSH 10.6 (released 2026-10-06) manual pages.
Check option names and defaults against `man sshd_config` on the target hosts.

## Reference map

| Concern | Reference |
| --- | --- |
| Server hardening, algorithms, drop-ins, audit logging | [sshd hardening](sshd-hardening.md) |
| Keys, agent, certificates, host verification, automation | [Keys, certificates, and automation](keys-and-certificates.md) |

## Choose an access path

| Option | Use when | Strengths | Watch for |
| --- | --- | --- | --- |
| Pipeline or configuration management | The task is repeatable | Reviewed, logged, no human shell | Pipeline identity privilege |
| Managed session service (Azure Bastion, cloud session managers) | Cloud VMs without public SSH | No inbound port, identity-provider login, session logs | Service cost; native-client features per SKU |
| Just-in-time port opening | Occasional direct SSH from known addresses | Port closed by default, time-bound | Rule cleanup; source address accuracy |
| Bastion host with ProxyJump | Self-managed networks | Single hardened entry point | Bastion becomes a high-value target; patch and monitor it |
| Direct public SSH | Never for production | None worth the exposure | Constant scanning and credential stuffing |

Prefer the first row that fits. Interactive access is an exception path:
it needs a reason, an approval, a time limit, and a record.

## Ownership

- Opening network rules, issuing certificates, logging in to shared or
  production hosts, and changing `sshd_config` there are operator actions.
- An authoring or review session prepares templates, worksheets, and checks;
  it does not connect to production or change access rules.

## Quality gates

- No password or keyboard-interactive login; no root login.
- Logins restricted with `AllowGroups` or `AllowUsers`.
- Host keys verified (`StrictHostKeyChecking yes` with distributed keys or a
  host certificate authority); never disabled.
- No agent forwarding; ProxyJump for multi-hop access.
- Keys are ed25519 (or hardware-backed `-sk`) with passphrases; short-lived
  certificates where a CA exists.
- `LogLevel VERBOSE` and central log shipping; managed session logs retained.
- Automation keys are restricted (`restrict`, `command=`, `from=`) and rotated.
- No private key, passphrase, or internal host inventory in version control.

## Failure modes

| Symptom | Cause |
| --- | --- |
| Hardening appears applied but passwords still work | A later file sets the value first; check `sshd -T` and include order |
| Locked out after reload | Config error or `AllowGroups` without members; no second session kept open |
| ProxyJump fails with "administratively prohibited" | Jump host has `AllowTcpForwarding no` |
| Host key warning ignored, then accepted | No distributed known_hosts or host CA; operators trained to click through |
| Compromised jump host reads operator keys | Agent forwarding was enabled |
| Old key still works after an operator leaves | Long-lived keys without inventory or revocation |
| sshd refuses to start after an algorithm change | Algorithm name unknown to the installed OpenSSH version |

## Anti-patterns

- `StrictHostKeyChecking no` or `UserKnownHostsFile /dev/null` in scripts.
- Shared accounts or shared private keys.
- Private keys without passphrases on laptops.
- Keys copied into container images, CI variables in plain text, or repositories.
- `PermitRootLogin prohibit-password` as the "secure" setting.

## Verification

1. `python check_sshd_config.py --require-baseline <drop-in>` exits 0.
2. On a test host: `sshd -t`, then `sshd -T` shows the intended effective values.
3. Password login is refused: `ssh -o PubkeyAuthentication=no host` fails.
4. `ssh -G host` shows `forwardagent no` and `stricthostkeychecking yes`.
5. A user outside the allowed group is refused; the refusal is logged.
6. A login appears in the central log with the key or certificate fingerprint.
7. Fill the [runbook worksheet](../assets/remote-access-runbook.md.template).

## Primary sources

- <https://man.openbsd.org/sshd_config>
- <https://man.openbsd.org/ssh_config>
- <https://man.openbsd.org/ssh-keygen>
- <https://man.openbsd.org/sshd#AUTHORIZED_KEYS_FILE_FORMAT>
- <https://www.openssh.com/releasenotes.html>
- <https://learn.microsoft.com/azure/bastion/bastion-overview>
- <https://learn.microsoft.com/azure/defender-for-cloud/just-in-time-access-usage>
- <https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html>
