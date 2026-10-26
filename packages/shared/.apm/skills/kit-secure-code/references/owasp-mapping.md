# OWASP mapping for Python application code

Use the OWASP Top 10 as the awareness list and the Application Security
Verification Standard (ASVS) as the testable requirement set. The table maps
each Top 10:2025 category to the ASVS 5.0 chapters and to concrete Python
controls in this skill. Review date: 2026-10-23.

## Top 10:2025 to controls

| Top 10:2025 | ASVS 5.0 chapters | Python controls | Detection |
| --- | --- | --- | --- |
| A01 Broken Access Control | V8 Authorization | deny by default; check ownership on every object access server-side; contained file paths | tests per role and per foreign object id |
| A02 Security Misconfiguration | V13 Configuration | debug off, no default credentials, explicit CORS and headers, settings validated at startup | configuration tests, Ruff `S104`, `S201` |
| A03 Software Supply Chain Failures | V15 Secure Coding and Architecture | locked, audited dependencies; no install-time code without review | lockfile audit (`kit-supply-chain` skill) |
| A04 Cryptographic Failures | V11 Cryptography, V12 Secure Communication | `secrets` for tokens, Argon2id or bcrypt for passwords, TLS verification on | Ruff `S311`, `S324`, `S501` |
| A05 Injection | V1 Encoding and Sanitization, V2 Validation | parameterized SQL, argument-list subprocess, autoescaped templates, escaped LDAP filters | Ruff `S602`-`S611`, `S701`; secure pattern checker |
| A06 Insecure Design | V15, V2 Business Logic | threat model, rate limits, abuse cases as tests | threat model review |
| A07 Authentication Failures | V6 Authentication, V7 Session Management, V9 Self-contained Tokens, V10 OAuth and OIDC | proven libraries, constant-time comparison, token expiry and audience checks | integration tests against the identity provider |
| A08 Software or Data Integrity Failures | V15, V5 File Handling | no `pickle`/`marshal` on untrusted data, signed artifacts, safe YAML and XML | Ruff `S301`, `S506`, `S314`-`S320` |
| A09 Security Logging and Alerting Failures | V16 Security Logging and Error Handling | structured security events, redaction, no secrets in logs | log-capture tests |
| A10 Mishandling of Exceptional Conditions | V16 | fail closed, specific exceptions, no stack traces to callers | Ruff `BLE`, `S110`, `S112` |

Server-side request forgery, formerly its own category, is part of A01 in the
2025 list; it is still handled with the SSRF controls in
[secure patterns](secure-patterns.md).

## Choosing an ASVS level

| Exposure | Level | Meaning |
| --- | --- | --- |
| Internal tool, trusted operators, no sensitive data | Level 1 as a checklist | basic hygiene; most controls are cheap |
| Service reachable by untrusted callers, or handling personal data | Level 2 | the default target for production services |
| High-value data (payments, health, credentials at scale) | Level 3 | deep verification and design review |

Record the chosen level in the threat model. An internal tool still needs
injection-safe subprocess and path handling: its inputs often come from files
or other systems that an attacker can influence.

## Using the mapping in review

1. List each sink the change touches (database, shell, file system, network,
   deserializer, template, log).
2. Find its row, apply the control, and add a negative test.
3. Note the ASVS requirement identifiers in the threat model only when the
   project tracks them; do not invent compliance claims.

## Primary sources

- OWASP, [Top 10:2025](https://top10.owasp.org/2025/)
- OWASP, [Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/)
- OWASP, [Cheat Sheet Series](https://cheatsheetseries.owasp.org/)
- Ruff, [flake8-bandit rules](https://docs.astral.sh/ruff/rules/#flake8-bandit-s)
