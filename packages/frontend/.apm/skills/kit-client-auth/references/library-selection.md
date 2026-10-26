# Library selection for browser authentication

Reviewed 2026-10-23. Re-check maintenance signals at adoption time; they
change faster than this document.

## Selection criteria

| Criterion | Accept | Reject |
| --- | --- | --- |
| Protocol support | Authorization code with PKCE `S256`, `state`, `nonce`, refresh token rotation | Implicit grant as the default path |
| Certification | OpenID Foundation certified relying party, or provider-maintained SDK | Unknown provenance |
| Maintenance | Releases within the last six months, responsive security advisories, more than one maintainer | Archived, single inactive maintainer, unanswered advisories |
| Storage control | Pluggable storage; in-memory default possible | Forces tokens into `localStorage` |
| Types and modules | Ships TypeScript types and ESM | Requires polyfills or global scripts |
| Size | Fits the bundle budget from `kit-frontend-build` | Pulls large crypto shims |
| Logout | RP-initiated logout support | No end-session support |

A BFF needs no browser OAuth library at all: the browser calls the BFF's
login, user, and logout endpoints. Prefer that when the architecture allows.

## Common choices

| Library | Fits | Notes |
| --- | --- | --- |
| `oidc-client-ts` | Any standards-compliant OpenID Connect provider | Version 3.5 (March 2026) uses `crypto.subtle`, so it needs a secure context (HTTPS or localhost). Configure `userStore` with in-memory storage (`InMemoryWebStorage`) and `automaticSilentRenew` with refresh tokens rather than iframes. Companion `react-oidc-context` provides hooks. |
| MSAL Browser and MSAL React | Microsoft Entra ID and Entra External ID | Provider-maintained. Set `cache.cacheLocation` to `memoryStorage` or `sessionStorage` per the threat model; acquire tokens with `acquireTokenSilent` and fall back to interactive only on `InteractionRequiredAuthError`. Do not mix MSAL with a second OIDC library for the same provider. |
| Provider SDKs from other identity vendors | That vendor only | Accept only when maintained by the vendor and configurable as above |

## Adoption checks

1. Record version, release date, open security advisories, and license in the
   threat checklist.
2. Confirm redirect URIs, scopes, and token lifetimes with the identity
   provider configuration owner.
3. Wrap the library behind the auth provider template so components depend on
   the context interface, not the library.
4. Test callback errors, renewal failure, and logout with a fake provider; run
   one flow against a non-production tenant before release.

## Primary sources

- oidc-client-ts: <https://github.com/authts/oidc-client-ts>
- oidc-client-ts migration notes: <https://github.com/authts/oidc-client-ts/blob/main/docs/migration.md>
- react-oidc-context: <https://github.com/authts/react-oidc-context>
- MSAL for JavaScript: <https://github.com/AzureAD/microsoft-authentication-library-for-js>
- MSAL Browser caching: <https://learn.microsoft.com/en-us/entra/msal/javascript/browser/caching>
- OpenID certified implementations: <https://openid.net/developers/certified-openid-connect-implementations/>
- RFC 10017 section 6.1, BFF pattern: <https://www.rfc-editor.org/rfc/rfc10017#section-6.1>
