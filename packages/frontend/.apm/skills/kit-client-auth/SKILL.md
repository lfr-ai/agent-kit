---
name: kit-client-auth
description: Use when adding OIDC sign-in, token renewal, logout, route guards or 401/403 handling to a browser application.
license: MIT
---

# Authenticate a browser application safely

## Resources

- [Client authentication guide](references/guide.md): architecture choice,
  authorization code with PKCE, token storage, renewal, logout, CSRF, error
  handling, failure modes, primary sources.
- [Library selection](references/library-selection.md): criteria, maintenance
  signals, and configuration notes for `oidc-client-ts` and MSAL.
- [Threat checklist](assets/threat-checklist.md.template) to fill per change.
- Templates: [auth provider and context](assets/auth-provider.tsx.template),
  [API fetch interceptor](assets/auth-fetch.ts.template) with
  [tests](assets/auth-fetch.test.ts.template),
  [route guard and role-aware UI](assets/route-guard.tsx.template).
- Related owners: the typed HTTP client in `kit-state-data` (pass the
  interceptor as its `fetchImpl`), safe return paths and error boundaries in
  `kit-routing`, public client settings in `kit-runtime-config`, and
  server-side token validation and authorization in the backend `kit-auth`
  skill when that bundle is selected.

## Procedure

1. Read the guide; fill the threat checklist before writing code.
2. Choose the architecture with the decision table: a backend-for-frontend
   (BFF) with an HTTP-only session cookie for applications handling sensitive
   data; a browser-based OAuth client only when no backend can hold tokens.
3. Use the authorization code flow with PKCE (`S256`), `state`, and `nonce`;
   never the implicit or password grants. Register exact redirect URIs.
4. Use a maintained certified library; do not hand-roll protocol handling.
5. Store tokens outside script-readable persistent storage: BFF cookies, or
   in-memory access tokens for browser clients. Never put refresh tokens in
   `localStorage` or `sessionStorage`.
6. Renew through refresh token rotation or the BFF session; handle renewal
   failure as signed out with a visible prompt, not a silent loop.
7. Protect cookie-authenticated unsafe requests with `SameSite` cookies plus a
   CSRF token or required custom header; keep CORS origins exact.
8. On 401, attempt one coordinated renewal and retry once; on 403, show an
   access message and keep the session. Never retry indefinitely.
9. Treat route guards and role-based UI as navigation aids; the API authorizes
   every request and must reject what the UI hides.
10. Implement logout that clears local state and caches, ends the server
    session, and calls the provider end-session endpoint when required.
11. Test sign-in, callback errors, expired sessions, concurrent 401s, 403,
    logout in another tab, and open-redirect attempts with fake providers.
12. Report which flows ran against a real identity provider; mocked flows
    prove client logic only.

## Acceptance gates

- [ ] Architecture choice and token storage are recorded in the checklist.
- [ ] Code flow with PKCE `S256`, `state`, and `nonce`; no implicit grant.
- [ ] No tokens in persistent web storage, URLs, logs, or error reports.
- [ ] Concurrent 401s trigger a single renewal; 403 does not sign out.
- [ ] Unsafe cookie requests carry CSRF protection; return paths are validated.
- [ ] Logout clears client caches and ends the server and provider session.
