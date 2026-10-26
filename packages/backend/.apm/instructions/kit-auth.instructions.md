---
description: Apply to authentication, authorization, and token-handling modules.
applyTo: "**/auth/**/*.py,**/security/**/*.py"
---

- Verify bearer tokens with a fixed allow-list of asymmetric algorithms configured next to the key source; never take the algorithm from the token, never allow `none` or HMAC with public keys.
- Validate `iss` and `aud` exactly, require `exp`, and keep clock leeway at two minutes or less.
- Resolve keys by `kid` from a cached JWKS with a bounded refetch; never follow `jku`, `x5u`, or embedded keys.
- Keep roles, permissions, and scopes in closed enumerations or mappings; unknown claim values grant nothing.
- Return 401 with `WWW-Authenticate` for missing or invalid credentials and 403 for authenticated callers without permission.
- Never log, print, or echo tokens, `Authorization` headers, or full claim sets; log rejection reasons only.
- Test with locally generated keys; never disable signature verification in tests.
- Use the `kit-auth` skill for flows, verifier wiring, and the threat checklist.
