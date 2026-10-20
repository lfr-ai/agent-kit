# Public value boundaries

## The rule

Anything shipped to a browser (JavaScript, CSS, HTML, JSON, source maps, images,
service worker caches) is readable by every user and every script on the page.
Obfuscation, minification, environment checks, and unusual names do not change
that.

## Classification

| Value | Public? | Where it lives |
| --- | --- | --- |
| API base URL, environment name, build version | yes | runtime config |
| Feature flags that only change presentation | yes | runtime config or flag service |
| OAuth/OIDC client id, authority URL, redirect URI for a public client | yes | runtime config |
| Telemetry ingestion key designed for browsers | yes, by vendor design | runtime config; restrict by origin at the vendor |
| Maps or search keys restricted by HTTP referrer | yes, if restriction is enforced | runtime config; verify the restriction |
| OAuth client secret | no | backend only; public clients use PKCE |
| Database or storage connection strings | no | backend only |
| Signing keys, private keys, webhook secrets | no | backend secret store |
| Third-party API keys without origin restriction | no | backend proxy |
| Internal host names, admin URLs, internal IP ranges | no | backend configuration |
| Authorization rules | not trusted | enforced by the API; the client may mirror them for UX |

When unsure, treat the value as private and call it through the backend.

## Feature flags are not access control

Hiding a button behind a flag or role check improves UX; it does not protect the
operation. The API must reject unauthorized calls regardless of the client state.

## Review checklist for a new configuration value

1. Who needs the value, the browser or the server?
2. What can an attacker do with it if it is public?
3. Is it restricted (origin, referrer, scope, quota) by the issuer, and was that
   restriction verified?
4. Is it added to the strict schema with a narrow type?
5. Is it present in each environment's `config.json` and validated in the
   pipeline?
6. Does the CSP or CORS configuration need a matching change?

## Leak response

If a private value reached a public artifact:

1. Treat it as compromised; rotation is an operator action outside this
   procedure, triggered immediately.
2. Remove the value from source, configuration, and build caches; rebuild.
3. Purge CDN caches and published source maps; note that clients and archives may
   retain copies.
4. Add a deny pattern or rule to the bundle scanner so the class of leak fails the
   pipeline next time.

## Acceptance gates

- [ ] Every configuration key is classified with the table above.
- [ ] No private value appears in source, `.env` files committed to the
      repository, or the build output scan.
- [ ] Restricted public keys have verified restrictions.
- [ ] Authorization is enforced server-side for every flagged feature.

## Sources

- OWASP, secrets management: <https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html>
- OAuth 2.0 for browser-based applications (IETF draft): <https://datatracker.ietf.org/doc/draft-ietf-oauth-browser-based-apps/>
- RFC 7636, PKCE: <https://www.rfc-editor.org/rfc/rfc7636.html>
- Vite, env variables security note: <https://vite.dev/guide/env-and-mode>
- MDN, Content Security Policy: <https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP>
- MDN, CORS: <https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS>
