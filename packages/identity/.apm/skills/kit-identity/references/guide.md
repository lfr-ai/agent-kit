# Entra, OIDC and application authorization

Primary sources checked 2026-11-02 without credentials. This is original
integration guidance, not vendored provider implementation.

## Trust and flow choices

| Caller | Flow / responsibility |
| --- | --- |
| Sensitive browser app | Prefer BFF, server token cache, Secure HttpOnly host-only session cookie and CSRF defense |
| SPA without BFF | MSAL Browser/React for Entra, maintained OIDC client otherwise; code flow with PKCE S256, state and nonce |
| Backend user flow | Confidential code client; secret/certificate stays server-side; exact registered redirect |
| App-only worker | Client credentials/workload identity; API application roles, not delegated user scopes |
| API resource server | Verify its access token and enforce action/resource/tenant policy; no login redirect in an API 401 |

PKCE binds the authorization code to the verifier, state binds the callback to
the initiating session, and nonce binds the verified ID token to that login.
None substitutes for the others. Require short-lived, high-entropy library-owned
transactions; atomically consume them even on failure. Reject code reuse,
expired transactions and mismatched redirects; exact registered redirects and a
same-origin relative post-login return path are separate checks. Public clients
have no client secret. Do not use implicit/password grants.

## API adapter and errors

Use a reviewed JWT/OIDC library in infrastructure. Configure the trusted
discovery URL rather than accepting arbitrary `jku`/`x5u` or issuer URLs from a
token (SSRF/key-confusion risk). Bound metadata requests; cache supported keys
and refresh unknown `kid` at most once under a refresh lock/rate limit. On
rotation accept only issuer-scoped trusted keys and valid signatures. Stale-key
availability is an explicit library policy, never "skip signature on outage".

Entra v1/v2 metadata and issuer forms differ. Match metadata to token version;
validate signature and algorithm allow-list, issuer, intended API audience,
tenant allow-list, expiry/not-before with a small configured skew. In a
multi-tenant app, validate tenant/issuer and key-issuer binding explicitly;
`common` discovery is not permission to accept every tenant. Graph-audience
tokens and ID tokens are not access tokens for your API.

The `TokenVerifier` port returns `VerifiedAccess` only after all checks. The
stdlib asset cannot verify signatures, parse JWTs or supply a vendor adapter.
The real adapter must chain concrete library failures using `from`, not catch
every exception and disguise programming defects as bad credentials.

| Error | Presentation contract | Retry / logging |
| --- | --- | --- |
| `UnauthenticatedError` | 401 and an appropriate Bearer challenge | One safe client renewal; do not expose validation details |
| `ForbiddenError` | 403 | No refresh or retry; authenticated but insufficient permission |
| `IdentityUnavailableError` | 503 | Fail closed; bounded upstream retry only, never ask users to relogin as a fix |
| `InvalidCallbackError` | Safe 400 / sign-in error view | Transaction consumed; no open redirect or automatic sign-in loop |

Log once at the handling boundary with safe reason code and operation; no
access/ID/refresh token, code, verifier, user claim or raw exception message.
Do not log an entire request or callback URL.

## Permission policy

`AccessGate.require` requires **all** configured delegated scopes and **any**
configured app role, with the two conditions combined by AND. Empty scopes or
roles explicitly disable that constraint; empty both means authentication-only
and is unsuitable for protected actions unless resource policy supplies the
authorization. App-only callers normally have roles without `scp`; configure a
separate app-only rule, do not silently OR delegated and application identities.
Entra `roles` are application roles; directory roles (`wids`), display names,
email, and unexpanded group-overage claims are not substitutes.

Validate tenant and resource ownership on every action even after the gate.
Frontend route guards merely improve navigation. Prefer framework dependencies
or callbacks that resolve verified claims once per request; if a decorator is
necessary, use `functools.wraps`, retain async behavior and avoid storing
request-local identity on a shared instance. Wire adapters at composition only.

## Supported MSAL caching

MSAL Browser supports `sessionStorage` (documented default), `localStorage` and
`memoryStorage`. Select a supported option for the version and threat model;
memory trades reload/cross-tab behavior for reduced persistence. Do not impose
a blanket prohibition on MSAL's own supported caches or copy refresh tokens to
a hand-built store. No cache is XSS-proof; local cache encryption is not a
defense against an attacker executing in the origin. Protect scripts, CSP and
dependencies, and clear user/query caches on logout.

Use `acquireTokenSilent` through the same provider instance and coordinate
interaction-required fallback; arbitrary networking errors are not an excuse
to launch repeated interactive redirects. Preserve MSAL callback/temporary-cache
semantics; do not invent a second state/nonce store in production.

## Verification and limits

The focused repo tests load `access_policy.py.template` using stdlib `runpy`
and exercise matching/mismatched callback bindings, expiry, issuer/audience
defense-in-depth, roles/scopes and verifier failure propagation. Re-run:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/unit/repo_guards/test_identity_resources.py
```

In the consumer, add real-library tests for wrong signature, disallowed
algorithm, expired/not-yet-valid token, unknown/rotated `kid`, wrong issuer,
audience and tenant, ID-token rejection, metadata outage and app-only rules.
Test callback replay against the library's atomic transaction store (the pure
callback function does not implement one). Test concurrent 401 single-flight,
second-401 expiry, 403 no retry and logout with browser tools. No Entra,
cryptographic-verifier or browser runtime has been verified here.

## Primary sources

- [Entra authorization code / PKCE](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Access-token validation, issuer and audience](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens)
- [Entra access-token claims](https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference)
- [MSAL Browser caching](https://learn.microsoft.com/en-us/entra/msal/javascript/browser/caching)
- [MSAL acquire tokens](https://learn.microsoft.com/en-us/entra/msal/javascript/browser/acquire-token)
- [OIDC Core validation](https://openid.net/specs/openid-connect-core-1_0.html)
- [OAuth security BCP, RFC 9700](https://www.rfc-editor.org/rfc/rfc9700)
- [PKCE, RFC 7636](https://www.rfc-editor.org/rfc/rfc7636)
- [Browser-based apps, RFC 10017](https://www.rfc-editor.org/info/rfc10017)
