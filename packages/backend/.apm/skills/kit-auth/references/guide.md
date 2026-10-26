# API authentication guide: failure modes, anti-patterns, verification

Reviewed 2026-10-23. Detail: [OAuth and OIDC](oauth-oidc.md),
[JWT validation](jwt-validation.md), and
[authorization and status codes](authorization-and-errors.md).

## Failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Forged tokens accepted | `alg` taken from the token, `none` allowed, or HS and RS mixed | Fixed asymmetric allow-list checked before key lookup |
| Tokens for another API accepted | No or loose `aud` check | Exact audience for this API |
| All requests fail after key rotation | Keys cached without expiry or no refetch on unknown `kid` | Expiring cache plus bounded refetch |
| Issuer flooded by JWKS requests | Refetch on every unknown `kid` | Minimum refetch interval |
| Event loop stalls under load | Blocking key fetch inside `async def` | Sync dependency or prefetched keys |
| Users see each other's data | Only route-level permissions checked | Object-level checks in use cases |
| Tokens visible in logs or traces | Logging headers or request dumps | Log reasons only; scrub `Authorization` in log and trace processors |
| Clients cannot recover from 401 | Missing `WWW-Authenticate` | RFC 6750 header on every 401 and scope 403 |

## Anti-patterns

- Validating tokens by calling the issuer's userinfo endpoint per request.
- Accepting ID tokens as access tokens.
- Long leeway (minutes) to hide clock drift; fix time synchronization.
- Authorization decisions based on email addresses or display names.
- Shared HMAC secrets between the issuer and many APIs.
- Test suites that disable verification (`verify_signature=False`) instead of
  signing tokens with locally generated keys.

## Verification

```text
pytest tests/auth -q
```

The [test template](../assets/test_auth.py.template) covers valid tokens,
expiry with and without leeway, `nbf`, audience, issuer, missing claims,
`alg: none`, HMAC confusion, unknown `kid`, wrong key, wrong `typ`, unsafe
policies, the authorization matrix, 401 and 403 headers, and token-free logs.
Complete the [threat checklist](../assets/threat-checklist.md.template) for
each new API or issuer. File tests do not prove the live issuer's metadata,
key rotation timing, or gateway behavior; verify those in an integration
environment.

## Primary sources

- [RFC 9700: OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html)
- [RFC 8725: JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
