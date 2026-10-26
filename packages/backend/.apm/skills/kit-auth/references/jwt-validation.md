# Bearer JWT validation

Reviewed 2026-10-23 against RFC 7519, RFC 8725 (JWT Best Current Practices),
RFC 9068, and the PyJWT documentation. Implemented by
[tokens.py.template](../assets/tokens.py.template).

## Validation order

1. Parse the `Authorization: Bearer <token>` header. Reject tokens in query
   strings or cookies unless a reviewed design requires them.
2. Read the unverified header. Reject when `alg` is not in the configured
   allow-list, and when `typ` is not `at+jwt` for RFC 9068 tokens. Never
   derive the allowed algorithms from the token.
3. Resolve the key by `kid` from the issuer's JWKS (cached). Never follow
   `jku`, `x5u`, or embedded `jwk` header parameters.
4. Verify the signature with the allow-listed algorithms.
5. Validate `iss` (exact match), `aud` (contains this API), `exp`, `nbf`,
   and `iat` with a small leeway (30 to 60 seconds), and require the claims
   the API relies on (`sub`, `exp`, `iat`, `iss`, `aud`; RFC 9068 also lists
   `client_id` and `jti`).
6. Map claims to a principal with a closed policy
   ([authorization](authorization-and-errors.md)).

## Algorithm rules (RFC 8725)

| Rule | Why |
| --- | --- |
| Allow-list asymmetric algorithms only (`RS256`, `PS256`, `ES256`, `EdDSA`) | A resource server holds public keys only |
| Never allow `none` | Unsigned tokens would be accepted |
| Never mix `HS*` with `RS*`/`ES*` for one key source | HMAC verification with a public key as the secret lets anyone forge tokens |
| Pin the algorithm per key when the JWKS states `alg` | Stops cross-algorithm use of one key |

`JwtPolicy` rejects unsafe allow-lists at construction, so a configuration
error fails startup instead of weakening validation.

## Keys, caching, and rotation

- Discover `jwks_uri` from the issuer metadata once at startup; pin the HTTPS
  URL in configuration rather than trusting values in tokens.
- Cache the key set (minutes). On an unknown `kid`, refetch once, then wait a
  minimum interval before the next forced refetch; otherwise random `kid`
  values become a denial-of-service against the issuer and the API.
  Recent PyJWT releases add a `cooldown_duration` to `PyJWKClient`; check the
  installed version before relying on it. The template bounds refetches itself.
- Issuers publish the next key before signing with it and keep the old key
  until tokens signed with it expire; the cache lifetime must be shorter than
  that overlap.
- Key fetches block. Run verification in a sync dependency (worker thread) or
  prefetch keys in the lifespan and refresh them in a background task.
- When keys cannot be fetched, answer 503 with `Retry-After`, not 401; the
  client's token may be valid.

## Opaque tokens

When the issuer does not use JWT access tokens, validate by introspection
(RFC 7662) over an authenticated channel, cache positive results no longer
than the token lifetime, and treat `active: false` as invalid.

## Logging

Log the rejection reason (`expired`, `wrong_audience`) and the request id.
Never log the token, its signature, the `Authorization` header, or full claim
sets; `sub` may be personal data under your privacy rules.

## Primary sources

- [RFC 7515: JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515.html)
- [RFC 7517: JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517.html)
- [RFC 7519: JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html)
- [RFC 8725: JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html)
- [RFC 9068: JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html)
- [PyJWT: Usage](https://pyjwt.readthedocs.io/en/stable/usage.html)
- [PyJWT: API reference](https://pyjwt.readthedocs.io/en/stable/api.html)
- [OWASP JSON Web Token Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_Cheat_Sheet.html)
