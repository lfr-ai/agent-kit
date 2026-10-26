---
name: kit-auth
description: Use when adding or reviewing API auth such as OAuth or OIDC flows, JWT and JWKS validation, roles, or 401/403.
license: MIT
---

# Authenticate and authorize API requests

## Procedure

1. Identify the issuer, its metadata URL, the API's audience identifier, the
   token format, and every client and grant type. Choose grants with
   [OAuth and OIDC](references/oauth-oidc.md); never accept implicit or
   password grants.
2. Write failing tests first from the
   [test template](assets/test_auth.py.template): locally generated keys,
   one negative case per validation rule, and the 401 and 403 contract.
3. Define the token verifier port and adapter from
   [tokens.py](assets/tokens.py.template): fixed asymmetric algorithm
   allow-list, header check before key lookup, exact `iss` and `aud`,
   required claims, bounded leeway, cached JWKS with bounded refetch. Follow
   [JWT validation](references/jwt-validation.md).
4. Model roles, permissions, and scopes as a closed policy
   ([policy.py](assets/policy.py.template)); unknown claim values grant
   nothing. Add object-level checks in use cases, not only route permissions.
5. Wire [security dependencies](assets/security.py.template): build the
   verifier in the lifespan, authenticate in a sync dependency, and declare
   `require(Permission.X)` on every protected route. Apply the status rules
   in [authorization and errors](references/authorization-and-errors.md).
6. Keep tokens, `Authorization` headers, and full claim sets out of logs,
   traces, errors, and URLs; log only rejection reasons and request ids.
7. Load issuer, audience, algorithms, and JWKS URL through typed settings
   (`kit-config`); secrets such as client credentials stay in the secret store.
8. Complete the [threat checklist](assets/threat-checklist.md.template) and
   review the [failure modes](references/guide.md). Run the auth tests and the
   project gate.

## Acceptance gates

- `none`, HMAC algorithms, and algorithms outside the allow-list are rejected
  before any key lookup; a policy that allows them fails at startup.
- Tests cover expired, not-yet-valid, wrong issuer, wrong audience, missing
  claim, unknown `kid`, wrong key, and wrong `typ`, each with its reason.
- Missing or invalid credentials return 401 with `WWW-Authenticate`; valid
  callers without permission return 403 with `insufficient_scope`; key fetch
  outages return 503.
- Every protected route declares a permission; the authorization matrix and
  object-level ownership have tests.
- No token or `Authorization` header appears in logs, problem bodies, or
  exception messages; a test asserts it.
