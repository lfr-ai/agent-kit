---
name: kit-remote-access
description: Use when configuring or reviewing SSH access, sshd_config, keys, bastions, or ProxyJump.
license: MIT
---

# Configure and review remote access

Remote access is an exception path into running systems. Make it narrow,
verifiable, time-bound, and recorded. Start with the
[review guide](references/guide.md).

## Procedure

1. State why the task needs remote access instead of a pipeline or
   configuration management change, and record the approval.
2. Choose the access path from the guide's decision table: managed session
   service, just-in-time port, or bastion with ProxyJump. Never direct
   public SSH to production.
3. Check user keys and agents per
   [keys, certificates, and automation](references/keys-and-certificates.md):
   ed25519 or hardware-backed keys with passphrases, a bounded agent
   lifetime, no agent forwarding, and ProxyJump for every extra hop.
4. Check host verification: distributed known_hosts or a host certificate
   authority; reject `StrictHostKeyChecking no` and `/dev/null` known hosts.
5. Harden servers with the [sshd drop-in](assets/sshd-hardening.conf.template)
   and [sshd hardening](references/sshd-hardening.md): no passwords,
   keyboard-interactive, or root login; `AllowGroups`; modern algorithms for
   the installed version; `LogLevel VERBOSE`.
6. Run [check_sshd_config.py](assets/check_sshd_config.py) on changed files:

   ```text
   python check_sshd_config.py --require-baseline sshd_config.d/10-hardening.conf
   ```

   It exits 0 when clean, 1 with findings (`path:line: message`), and 2 for
   unreadable input. It does not follow `Include` or evaluate `Match`; confirm
   effective values with `sshd -T` on a test host.
7. Give operators the [client configuration](assets/ssh_config.template) with
   ProxyJump, `ForwardAgent no`, and strict host key checking.
8. Prefer short-lived SSH certificates or managed identity; restrict any
   automation key with `restrict`, `from=`, and `command=`, and keep it in a
   secret store.
9. Fill the [runbook worksheet](assets/remote-access-runbook.md.template) and
   hand the access, rule changes, and reloads to the named operator; keep
   one session open while reloading sshd.
10. After access, confirm temporary rules and certificates expired and the
    session record is attached.

## Acceptance gates

- No password, keyboard-interactive, or root login; logins restricted by group.
- Host keys verified; no disabled host key checking anywhere.
- No agent forwarding; multi-hop access uses ProxyJump.
- The sshd checker passes with `--require-baseline`, or each finding is justified.
- Audit logs show key or certificate fingerprints and reach a central store.
- No private keys or passphrases in version control, images, or tickets.
- A named operator performs access and records the session.

## Out of scope

This skill prepares and reviews configuration. It does not open network
rules, issue certificates, or log in to shared systems; those remain
operator-owned actions.
