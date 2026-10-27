# Keys, certificates, and automation

Reviewed 2026-10-23.

## User keys

| Choice | Recommendation |
| --- | --- |
| Algorithm | `ssh-keygen -t ed25519 -a 100`; hardware-backed `ed25519-sk` or `ecdsa-sk` where security keys are issued |
| Passphrase | Always; the agent holds the decrypted key for a bounded time |
| One key per | Person and device; never shared between people |
| RSA | Only for systems that cannot use ed25519; at least 3072 bits |
| Storage | `~/.ssh` with mode 0700 and key mode 0600; never synced to shared drives or repositories |

- Load keys with `AddKeysToAgent` and a lifetime (`1h`), or `ssh-add -t`.
- Use `IdentitiesOnly yes` so the client offers only the configured key and
  does not exhaust `MaxAuthTries` with every agent key.

## Agent forwarding versus ProxyJump

Agent forwarding lets any root user on the intermediate host use your agent
while you are connected. ProxyJump (`ssh -J bastion target`) opens a
tunnel through the bastion and authenticates end to end from your machine,
so the bastion never sees key material.

- Client: `ForwardAgent no` in `Host *`; `ProxyJump bastion` per target pattern.
- Bastion: `AllowTcpForwarding local`, `AllowAgentForwarding no`, no other tools.
- If forwarding is unavoidable for one host, scope it to that host block and
  use `ssh-add -c` so each use requires confirmation.

## Host key verification

Accepting an unknown host key is trusting whoever answered first.

| Approach | How | Notes |
| --- | --- | --- |
| Host certificate authority | Sign host keys (`ssh-keygen -s host_ca -h -I host -n names`); clients add `@cert-authority *.internal.example.invalid <ca.pub>` to `known_hosts` | Scales; rotation by re-signing |
| Distributed known_hosts | Configuration management writes `/etc/ssh/ssh_known_hosts` | Works without a CA; must track rebuilds |
| Managed session services | Service verifies the target | Confirm what the service validates |
| Trust on first use (`accept-new`) | Accepts the first key, rejects changes | Interactive convenience only; not for automation |

Never use `StrictHostKeyChecking no` or `UserKnownHostsFile /dev/null`. A
changed key is an incident until explained (rebuild, rotation, or attack).

## Short-lived SSH certificates

User certificates replace scattered `authorized_keys` entries with a CA that
the servers trust (`TrustedUserCAKeys`).

```text
ssh-keygen -s user_ca -I alice@change-1234 -n alice -V +8h \
  -O no-agent-forwarding -O no-x11-forwarding id_ed25519.pub
ssh-keygen -L -f id_ed25519-cert.pub
```

- Validity of hours, not months; principals match login names or roles.
- Keep the CA key offline or in a managed signing service; log every
  signature with key ID and serial.
- Revoke with `RevokedKeys` (key revocation list) for the rare case a
  certificate must die before it expires.

## Automation with least privilege

- Prefer the platform's identity (managed identity, workload identity,
  session manager) over SSH keys for pipelines.
- When a key is required, restrict it in `authorized_keys`:
  `restrict,from="10.0.0.0/24",command="/usr/local/bin/deploy-hook" ssh-ed25519 ...`.
  `restrict` disables forwarding, PTY, and user rc in one option.
- Store automation keys only in a secret store; issue per-run certificates
  when a CA exists; rotate on schedule and on staff changes.
- Pin host keys for automation in a committed known_hosts file containing
  only public keys of the intended hosts (no internal names in public repositories).

## Never commit

- Private keys, certificates with private material, or passphrases.
- `known_hosts` or `ssh_config` files that reveal internal topology to a
  public audience.
- Add `id_*`, `*.pem`, `*.key` patterns to ignore files and enable secret
  scanning; rotate immediately if a key was ever pushed, even if deleted later.

## Primary sources

- <https://man.openbsd.org/ssh-keygen>
- <https://man.openbsd.org/ssh-agent>
- <https://man.openbsd.org/ssh_config>
- <https://man.openbsd.org/sshd#AUTHORIZED_KEYS_FILE_FORMAT>
- <https://man.openbsd.org/sshd#SSH_KNOWN_HOSTS_FILE_FORMAT>
