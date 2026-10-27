# sshd hardening

Reviewed 2026-10-23 for OpenSSH 9.9 through 10.6.

## How sshd reads configuration

- For most keywords the first value read wins. Distributions start the main
  file with `Include /etc/ssh/sshd_config.d/*.conf`, so drop-ins override
  the main file, and lexically earlier drop-ins override later ones. A cloud
  image file such as `50-cloud-init.conf` can re-enable passwords if your
  file sorts after it; name yours `10-hardening.conf`.
- `Match` blocks apply to matching connections until the next `Match`; put
  global settings before the first `Match`.
- `sshd -t` checks syntax; `sshd -T` prints effective values (add
  `-C user=...,host=...,addr=...` to evaluate `Match` blocks).
- Reload with the service manager (`systemctl reload ssh` or `sshd`); existing
  sessions survive. Keep one session open until a new login succeeds.

## Directive table

| Directive | Value | Reason |
| --- | --- | --- |
| `PasswordAuthentication` | `no` | Stops password guessing |
| `KbdInteractiveAuthentication` | `no` | Usually a password prompt through PAM |
| `PermitRootLogin` | `no` | Forces named accounts and audited escalation |
| `AuthenticationMethods` | `publickey` (or `publickey,keyboard-interactive` for a second factor) | Makes the policy explicit |
| `AllowGroups` / `AllowUsers` | A dedicated group | Limits who can log in at all |
| `PermitEmptyPasswords`, `HostbasedAuthentication` | `no` | Legacy trust models |
| `AllowAgentForwarding` | `no` | Server cannot use client keys |
| `AllowTcpForwarding` | `no` on targets; `local` on jump hosts | ProxyJump needs local forwarding on the jump host |
| `X11Forwarding`, `PermitTunnel`, `GatewayPorts` | `no` | Remove unused tunnels |
| `PermitUserEnvironment` | `no` | Users cannot alter the login environment |
| `MaxAuthTries`, `LoginGraceTime` | `3`, `30` | Shorter brute-force windows |
| `ClientAliveInterval`, `ClientAliveCountMax` | `300`, `2` | Drop dead sessions |
| `LogLevel` | `VERBOSE` | Logs the key fingerprint for each login |
| `TrustedUserCAKeys` | CA public key path | Accept short-lived user certificates |

## Algorithms

Current OpenSSH defaults are already strong; pinning lists is mainly for
compliance or to remove fallbacks. If you pin them:

| List | Recommended order | Never allow |
| --- | --- | --- |
| `KexAlgorithms` | `mlkem768x25519-sha256`, `sntrup761x25519-sha512`, `curve25519-sha256` | Any `*-sha1` exchange |
| `Ciphers` | `chacha20-poly1305@openssh.com`, AES-GCM, AES-CTR | CBC modes, 3DES, arcfour, blowfish |
| `MACs` | `*-etm@openssh.com` SHA-2 variants | MD5, SHA-1, `umac-64` |
| `HostKeyAlgorithms`, `PubkeyAcceptedAlgorithms` | ed25519, ECDSA, `rsa-sha2-*` | `ssh-rsa` (SHA-1 signatures), `ssh-dss` |

`mlkem768x25519-sha256` exists from OpenSSH 9.9 and is the default from 10.0;
remove it on older servers, which refuse to start on unknown names. Check
supported names with `ssh -Q kex`, `ssh -Q cipher`, and `ssh -Q mac`.

## Audit logging

- `LogLevel VERBOSE` records the fingerprint of the key or certificate used.
- Ship `auth` logs to a central store that operators cannot alter.
- For privileged sessions, record commands through sudo logging or the
  managed session service; record who approved the session.
- Alert on logins outside the allowed group, root attempts, and logins
  outside change windows.

## Checker

`check_sshd_config.py` reports insecure values, legacy algorithms, and
ignored duplicates; `--require-baseline` also requires the core directives.
It does not follow `Include`, evaluate `Match` conditions, or read the
compiled-in defaults, so run `sshd -T` on a test host as well.

## Primary sources

- <https://man.openbsd.org/sshd_config>
- <https://man.openbsd.org/sshd>
- <https://www.openssh.com/releasenotes.html>
- <https://www.openssh.com/pq.html>
