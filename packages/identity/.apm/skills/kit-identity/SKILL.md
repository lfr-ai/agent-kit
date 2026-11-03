---
name: kit-identity
description: Use when integrating Entra or OIDC identity, API token verification and scope or role authorization.
license: MIT
---

# Verify identity before enforcing access

## Procedure

1. Read the [identity boundary guide](references/guide.md). Extend backend
   `kit-auth` or frontend `kit-client-auth` when selected; this package owns
   provider/flow decisions, not a second browser interceptor or JWT library.
2. Choose BFF/session for sensitive browser applications. For a SPA use the
   provider library, authorization code with PKCE `S256`, session-bound random
   `state`, ID-token `nonce`, exact registered redirects and a safe return path.
   Public clients cannot protect a client secret.
3. Let the library verify and atomically consume the callback transaction;
   reject missing/mismatched/reused/expired state, nonce, code and redirects.
   Clear callback URL parameters. Exempt the callback route from sign-in loops.
4. Configure trusted Entra tenant-specific discovery, API audience, token version
   and allowed algorithms at startup. Verify access-token signature with
   issuer-scoped JWKS, `iss`, `aud`, `exp`, `nbf` and tenant policy. Never use
   decode-only parsing, arbitrary token-supplied key URLs or ID tokens for APIs.
5. Normalize verified `scp` and `roles`; require delegated scopes and any
   configured application roles. App-only callers use application permissions,
   not an invented delegated scope. Authorize tenant/resource/action ownership
   independently; group overage and directory roles are not app role grants.
6. Adapt the [stdlib policy boundary](assets/access_policy.py.template). Inject
   a `TokenVerifier` Protocol through a keyword-only constructor; only the
   composition root creates a real library adapter. Its implementation is
   deliberately absent: this asset is not cryptographic verification.
7. Prefer a framework dependency/callback to authenticate once and pass verified
   claims into application policy. Use decorators only where framework-native:
   preserve async behavior, metadata and signatures, and test that no route can
   bypass the guard. Avoid a custom decorator framework.
8. Translate library exceptions to `UnauthenticatedError` or `IdentityUnavailableError`
   with `from`; the policy raises `ForbiddenError`. Map those only in presentation
   to 401 with appropriate challenge, 503, and 403 respectively. Log once with
   safe reason codes, never tokens, claims, codes, verifier or provider bodies.
9. Browser: `acquireTokenSilent` with MSAL's supported cache; interactive fallback
   only for interaction-required errors, coordinated once. On API 401 refresh
   once in single flight and retry once; on 403 show denial without renewal.
   Never automatically replay an unsafe operation unless its API contract
   guarantees pre-effect rejection or destination idempotency.
10. Test callback binding, denied permissions, token validation failures,
    unavailable keys, JWKS rotation, concurrent renewal and logout. Report
    library/tenant integration as unverified until run in an approved test tenant.

## Acceptance gates

- Callback state/nonce/redirect/expiry/reuse and code-verifier failures are denied.
- Wrong issuer/audience/signature/algorithm/time or ID-token input cannot reach
  authorization. Denied scope, app role or resource access returns 403, not 401.
- Supported MSAL caching is a documented threat-model choice, not a blanket ban.
- Mocked policy tests never claim Entra, signature or browser runtime coverage.
