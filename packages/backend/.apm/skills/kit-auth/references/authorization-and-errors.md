# Authorization, FastAPI dependencies, and 401 versus 403

Reviewed 2026-10-23. Implemented by
[policy.py.template](../assets/policy.py.template) and
[security.py.template](../assets/security.py.template).

## Closed policy

- Roles, permissions, and scopes are enumerations or fixed mappings in code.
  Unknown values from a token are dropped; they never grant anything.
- Roles grant permissions. For delegated tokens (a `scope` claim is present),
  a scope must also grant the permission, so a client cannot exceed what the
  user consented to. Application tokens without `scope` are judged by roles.
- Every route declares its permission with
  `Annotated[Principal, Depends(require(Permission.X))]`. A route without one
  is a review finding unless it is deliberately public (health, OpenAPI).
- Route permissions are function-level authorization. Object-level checks
  (does this subject own this order, is it in this tenant) belong in the use
  case, using `Principal.subject` and tenant claims, and need their own tests.
- Test the full matrix: every role and scope combination against every
  permission, including unknown roles and an empty token.

## FastAPI wiring

| Piece | Rule |
| --- | --- |
| `HTTPBearer(auto_error=False)` | Return `None` for a missing header so the API controls the 401 body and headers |
| `authenticate` | Sync `def`: key fetches may block; FastAPI runs it in a worker thread |
| `require(permission)` | Async dependency factory; raises 403 with `insufficient_scope` |
| Verifier | Built in the lifespan and read from lifespan state; tests inject one with local keys |
| OpenAPI | `HTTPBearer` registers the security scheme automatically |

The problem-details handler of `kit-fastapi-service` keeps `HTTPException`
headers, so `WWW-Authenticate` survives the conversion to
`application/problem+json`.

## Status semantics

| Situation | Status | Header |
| --- | --- | --- |
| No credentials | 401 | `WWW-Authenticate: Bearer realm="api"` |
| Malformed, expired, wrong issuer or audience, bad signature | 401 | `WWW-Authenticate: Bearer realm="api", error="invalid_token"` |
| Valid token, missing permission or scope | 403 | `WWW-Authenticate: Bearer error="insufficient_scope", scope="..."` |
| Valid token, object exists but belongs to someone else | 404 when existence is secret, else 403 | none |
| Issuer keys unavailable | 503 | `Retry-After` |
| Malformed `Authorization` request syntax | 400 | `WWW-Authenticate` with `error="invalid_request"` |

Keep 401 and 403 bodies generic. Do not tell the caller which claim failed.

## Primary sources

- [RFC 6750 section 3: The WWW-Authenticate response header](https://www.rfc-editor.org/rfc/rfc6750.html#section-3)
- [RFC 9110 section 15.5.2 (401) and 15.5.4 (403)](https://www.rfc-editor.org/rfc/rfc9110.html#name-401-unauthorized)
- [FastAPI: Security](https://fastapi.tiangolo.com/tutorial/security/)
- [FastAPI: OAuth2 scopes](https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/)
- [OWASP API Security Top 10 (2023): API1 Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP API Security Top 10 (2023): API5 Broken Function Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
