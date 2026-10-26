# Client authentication for browser applications

Reviewed 2026-10-23. The IETF guidance for browser-based OAuth clients was
published as RFC 10017 (BCP 212) in August 2026; earlier material cites it as
the draft "OAuth 2.0 for Browser-Based Apps". Confirm the provider's current
documentation for endpoint and cookie behavior before implementing.

## Choose the architecture first

| Pattern | Tokens live | Choose when | Main residual risk |
| --- | --- | --- | --- |
| Backend-for-frontend (BFF) | Server only; browser holds an HTTP-only, `Secure`, `SameSite` session cookie | Sensitive data, regulated domains, any app with a backend you control | CSRF and session riding; mitigated with SameSite, CSRF tokens, exact CORS |
| Same-domain session (no OAuth in browser) | Server session after OpenID Connect sign-in on the server | Frontend and API share an origin and owner | Same as BFF |
| Token-mediating backend | Backend obtains tokens; browser receives access tokens only | Calling third-party APIs directly from the browser is required | Stolen access tokens until expiry |
| Browser-based OAuth client | Browser obtains and holds tokens | No backend can be added; low-sensitivity data | Malicious script can acquire new tokens; keep lifetimes short |

RFC 10017 recommends the BFF pattern for business applications and sensitive
data because tokens never reach JavaScript. Record the decision and the data
classification in the threat checklist.

## Authorization code flow with PKCE

1. Generate a high-entropy `code_verifier`; send `code_challenge` with method
   `S256` (RFC 7636). Never use `plain`.
2. Send a random `state` and verify it on callback; send a `nonce` and verify
   it in the ID token. Bind both to the browser session that started the flow.
3. Register exact redirect URIs; no wildcards, no open redirect targets.
4. Exchange the code once; reject callbacks with unexpected `iss` (mix-up
   defense) when the provider returns it.
5. Remove the code, state, and any tokens from the URL and history right after
   the callback (`history.replaceState`).
6. Validate the post-login return path as same-origin and relative before
   navigating (use `safeReturnTo` from `kit-routing`).

The implicit grant and resource owner password grant are deprecated (RFC 9700)
and must not be used.

## Token storage trade-offs

| Storage | Readable by injected script | Survives reload | Verdict |
| --- | --- | --- | --- |
| HTTP-only cookie set by a BFF | No | Yes | Preferred |
| In-memory variable (closure, worker) | Indirectly, while the page runs | No | Acceptable for short-lived access tokens |
| `sessionStorage` | Yes | Per tab | Avoid for tokens |
| `localStorage` or IndexedDB | Yes | Yes | Never for refresh tokens; avoid for access tokens |

No storage choice survives a cross-site scripting compromise: an attacker can
act as the user while the page is open. Content Security Policy, output
encoding, and dependency hygiene remain the primary defense.

## Renewal, rotation, and expiry

- Browser clients: use refresh token rotation with reuse detection, short
  refresh lifetimes, and sender-constrained tokens (DPoP, RFC 9449) when the
  provider supports them. Iframe-based silent renew depends on third-party
  cookies and fails in many browsers; do not rely on it.
- BFF: the server renews tokens; the browser only sees session expiry.
- Renew a little before expiry, coordinate renewal across tabs (one leader or a
  `BroadcastChannel`), and treat renewal failure as signed out.
- Show the user that the session expired and preserve unsaved input where
  possible; never loop redirects.

## Logout

- Clear in-memory tokens, query caches, and user-scoped storage.
- End the server session (BFF logout endpoint, POST with CSRF protection).
- Call the provider end-session endpoint (OpenID Connect RP-Initiated Logout)
  with `id_token_hint` and a registered `post_logout_redirect_uri` when single
  sign-out is required.
- Propagate logout to other tabs and handle back-channel logout on the server.

## CSRF with cookies

- `SameSite=Lax` or `Strict`, `Secure`, `HttpOnly`, host-only cookies
  (`__Host-` prefix) for the session.
- Require a CSRF token or a custom request header (for example
  `X-CSRF: 1`) on unsafe methods; the server rejects requests without it.
- Exact CORS allow-lists; never reflect arbitrary origins with credentials.
- Never change state on `GET`.

## Guards, roles, and HTTP errors

| Situation | Client behavior | Server responsibility |
| --- | --- | --- |
| Unauthenticated navigation | Redirect to sign-in with validated `returnTo` | Reject API calls with 401 |
| 401 from API | One coordinated renewal, retry once, else signed-out state | Validate token or session on every request |
| 403 from API | Show "no access" with a way back; keep the session | Authorize per resource and action |
| Role-based UI | Hide or disable actions as a convenience | Enforce the same rule; never trust client roles |
| Expired session during form entry | Keep input; prompt to sign in again | Idempotent retry support where possible |

Roles in an ID token are claims for display decisions, not authorization.

## Failure modes

| Symptom | Cause | Repair |
| --- | --- | --- |
| Token visible in browser history or logs | Implicit grant or tokens in URL | Code flow; clean callback URL |
| Infinite redirect loop | Guard redirects while callback is processing | Exempt callback route; single in-flight sign-in |
| Many parallel refresh calls | Each 401 renews independently | Single-flight renewal promise |
| User signed out on 403 | 401 and 403 handled alike | Distinct handling |
| Silent renew stops working | Third-party cookie blocking | Refresh token rotation or BFF |
| Open redirect after login | Unvalidated `returnTo` | Same-origin relative path check |

## Primary sources

- RFC 10017, OAuth 2.0 for Browser-Based Applications: <https://www.rfc-editor.org/info/rfc10017>
- RFC 9700, Best Current Practice for OAuth 2.0 Security: <https://www.rfc-editor.org/rfc/rfc9700>
- RFC 7636, Proof Key for Code Exchange: <https://www.rfc-editor.org/rfc/rfc7636>
- RFC 9449, DPoP: <https://www.rfc-editor.org/rfc/rfc9449>
- RFC 6749, OAuth 2.0: <https://www.rfc-editor.org/rfc/rfc6749>
- OpenID Connect Core 1.0: <https://openid.net/specs/openid-connect-core-1_0.html>
- OpenID Connect RP-Initiated Logout 1.0: <https://openid.net/specs/openid-connect-rpinitiated-1_0.html>
- OWASP OAuth 2.0 Cheat Sheet: <https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html>
- OWASP CSRF Prevention Cheat Sheet: <https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html>
- OWASP Session Management Cheat Sheet: <https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html>
- OWASP HTML5 Security Cheat Sheet (web storage): <https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html>
