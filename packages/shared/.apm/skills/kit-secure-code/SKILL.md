---
name: kit-secure-code
description: Use when code handles untrusted input, files, subprocesses, outbound requests, deserialization, secrets or crypto.
license: MIT
---

# Write and review application code securely

## Procedure

1. State the exposure first: internal tool run by trusted operators, or a
   service reachable by untrusted callers. Exposure decides how strict each
   control must be ([threat modeling](references/threat-modeling.md)).
2. For a new entry point or trust boundary, fill the
   [threat model worksheet](assets/threat-model.md.template) with a STRIDE
   pass over each data flow; record accepted risks with an owner.
3. Map the change to the relevant OWASP Top 10 and ASVS requirements with the
   [OWASP mapping](references/owasp-mapping.md).
4. Validate untrusted input once, at the boundary, into typed values
   (allow-lists, bounds, lengths, formats); reject rather than repair.
5. Apply the [secure patterns](references/secure-patterns.md) for each sink
   the change touches: parameterized SQL, subprocess with argument lists and
   timeouts ([subprocess helper](assets/safe_subprocess.py.template)),
   contained paths ([path helper](assets/safe_paths.py.template)), SSRF
   allow-lists, safe deserialization, `defusedxml`, secrets, password hashing
   with Argon2id or bcrypt, the `secrets` module for tokens, safe temporary
   files, bounded regular expressions, and redacted logs.
6. Enable the security linters from the
   [static analysis reference](references/static-analysis.md): Ruff `S` rules
   ([configuration snippet](assets/ruff-security.toml.template)), Bandit or
   Semgrep in CI, and the
   [secure pattern checker](assets/check_secure_patterns.py) for the
   highest-risk calls.
7. Add negative tests for each control: malicious input is rejected, a path
   escape fails, a timeout fires, a secret never appears in logs.
8. Treat dependencies as attack surface: prefer the standard library or an
   existing dependency; review new ones with the `kit-supply-chain` skill.
9. Suppress a finding only with a specific rule code and a reason on the same
   line; never disable a rule family to pass.
10. Report what was checked, which findings remain accepted and why, and what
    needs a live test (authentication flows, deployed headers).

## Acceptance gates

- Exposure (internal or exposed) and trust boundaries are written down for
  new entry points; exposed services have a threat model with owners.
- Ruff `S` rules pass, or each suppression names the rule and a reason.
- `check_secure_patterns.py` reports no findings in changed files.
- No `shell=True`, `eval`/`exec` on input, `pickle` or `marshal` on untrusted
  data, unsafe YAML loading, `tempfile.mktemp`, or outbound HTTP without a
  timeout.
- Every external input is validated at the boundary, and negative tests prove
  rejection of malformed, oversized and traversal input.
- Passwords are hashed with Argon2id, scrypt or bcrypt; tokens come from
  `secrets`; no secret or personal data reaches logs or error responses.
