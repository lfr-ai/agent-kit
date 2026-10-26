# OAuth 2.0 and OpenID Connect for APIs

Reviewed 2026-10-23 against RFC 9700 (OAuth 2.0 Security Best Current
Practice) and OpenID Connect Core 1.0.

## Roles

| Term | In an API deployment |
| --- | --- |
| Authorization server (AS) | Issues tokens; publishes metadata (`/.well-known/openid-configuration` or RFC 8414) with `issuer` and `jwks_uri` |
| Client | Browser app, mobile app, CLI, or another service requesting tokens |
| Resource server | This API: validates access tokens and enforces authorization |
| Resource owner | The user whose data the client accesses |

The API is a resource server. It never handles passwords and never issues
its own tokens unless it is also the authorization server.

## Grant selection

| Client | Grant | Notes |
| --- | --- | --- |
| Browser SPA, mobile, desktop, CLI with a browser | Authorization code with PKCE (`S256`) | Public clients; PKCE is required by RFC 9700 for all clients |
| Server-rendered web app | Authorization code with PKCE and a client secret or private key JWT | Confidential client |
| Service calling an API on its own behalf | Client credentials | Prefer private key JWT or mTLS client authentication over shared secrets |
| Input-constrained device or headless CLI | Device authorization grant (RFC 8628) | Poll interval and expiry enforced by the AS |
| Implicit grant, resource owner password credentials | Do not use | Deprecated by RFC 9700 |

## Tokens

- Access token: for the API. Audience is the API. May be a JWT (RFC 9068,
  `typ: at+jwt`) or opaque (validate by introspection, RFC 7662).
- ID token (OIDC): for the client, describing the authentication event. The
  API must not accept it as an access token.
- Refresh token: for the client only; rotate or sender-constrain it for public
  clients. The API never sees it.
- Sender-constrained tokens (DPoP, RFC 9449; mTLS, RFC 8705) bind a token to a
  key held by the client and limit replay of stolen tokens. Adopt them when the
  AS supports them and the threat model includes token theft.

## Scopes and audiences

- Scopes express what a client was delegated (`items.read`); roles or groups
  express what a subject may do. A delegated request needs both.
- Request the narrowest scope; one audience per API. Reject tokens whose `aud`
  does not name this API, even when the issuer is trusted.

## Primary sources

- [RFC 6749: The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html)
- [RFC 6750: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html)
- [RFC 7636: Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636.html)
- [RFC 7662: Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html)
- [RFC 8414: Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html)
- [RFC 8628: Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628.html)
- [RFC 9068: JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html)
- [RFC 9449: DPoP](https://www.rfc-editor.org/rfc/rfc9449.html)
- [RFC 9700: OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
