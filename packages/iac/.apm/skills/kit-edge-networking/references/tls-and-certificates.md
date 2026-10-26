# TLS and certificates at the edge

Reviewed 2026-10-23 against Mozilla server-side TLS guidelines 6.0.

## Protocol and cipher profile

| Profile | Protocols | Use when | Notes |
| --- | --- | --- | --- |
| Modern | TLS 1.3 only | All clients are current browsers or controlled services | Simplest; no cipher list to maintain |
| Intermediate | TLS 1.2 and 1.3 | Default for public services | ECDHE with AES-GCM or ChaCha20-Poly1305 only; no CBC, no RSA key exchange |
| Old | Down to TLS 1.0 | Never for new services | TLS 1.0 and 1.1 are deprecated by RFC 8996 |

- Generate the configuration for the exact server and TLS library versions
  at <https://ssl-config.mozilla.org/>; do not hand-edit cipher strings.
- Guidelines 6.0 lists `X25519MLKEM768` first among key exchange groups. It
  needs OpenSSL 3.5 or newer (nginx), a current Go toolchain (Caddy,
  Traefik), or platform support; remove it where the library rejects it.
- Let clients choose the cipher order (`ssl_prefer_server_ciphers off`)
  when every offered cipher is strong.
- Disable session tickets unless ticket keys are rotated; a long-lived ticket
  key undoes forward secrecy.

## Certificates

- Automate issuance and renewal with ACME (Caddy and Traefik built in;
  certbot, lego, or a platform integration for nginx). Renew at about
  two thirds of the lifetime and alert well before expiry.
- Public certificate lifetimes are shrinking under CA/Browser Forum rules
  (maximum validity reduced in steps from 2026 onward). Treat any manual
  renewal step as a defect.
- Serve the full chain (leaf plus intermediates), never the root.
- Prefer ECDSA P-256 keys; keep RSA 2048 only for old clients.
- Private keys: readable only by the proxy user, never baked into images,
  never in version control; prefer a secret store or managed certificates.
- Use HTTP-01 challenges only when port 80 reaches the proxy; use DNS-01 for
  wildcards or private hosts, with a DNS token scoped to the challenge record.

## Revocation and OCSP stapling

- Stapling requires an OCSP URL in the certificate. Let's Encrypt removed OCSP
  URLs in May 2025 and turned off its responders in August 2025; other CAs
  may follow. With such certificates, leave stapling off and rely on CRLs.
- Check a certificate with `openssl x509 -in fullchain.pem -noout -ocsp_uri`.
  Enable `ssl_stapling` only when it prints a URL, and verify with
  `openssl s_client -status`.
- Caddy staples automatically when an OCSP URL exists.
- Do not request the OCSP Must-Staple extension from CAs that dropped OCSP.

## HSTS

HSTS tells browsers to refuse plain HTTP for the host. It is easy to add and
hard to undo, because browsers cache it for `max-age` seconds.

1. Serve every path over HTTPS and redirect HTTP first.
2. Start with `max-age=300`, then raise in steps (one week, one month) to
   63072000 seconds (two years).
3. Add `includeSubDomains` only after inventorying every subdomain.
4. Add `preload` and submit to the preload list only with owner approval;
   removal takes months.
5. Send the header only over HTTPS and on every response (`always` in nginx).

## Failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Some clients cannot connect after hardening | They only support TLS 1.0/1.1 or legacy ciphers | Confirm with access logs; upgrade clients or isolate them |
| nginx fails to start after a profile update | Library does not know a group or cipher name | Generate for the installed OpenSSL version |
| Certificate expired in production | Renewal failed silently | Alert on expiry days; test renewal in staging |
| Stapling warnings in the error log | Certificate has no OCSP URL | Disable stapling for that certificate |
| Subdomain unreachable in browsers | `includeSubDomains` added before it served HTTPS | Fix the subdomain; wait out the max-age |

## Primary sources

- <https://ssl-config.mozilla.org/>
- <https://wiki.mozilla.org/Security/Server_Side_TLS>
- <https://www.rfc-editor.org/rfc/rfc8446>
- <https://www.rfc-editor.org/rfc/rfc8996>
- <https://www.rfc-editor.org/rfc/rfc6797>
- <https://www.rfc-editor.org/rfc/rfc8555>
- <https://letsencrypt.org/2024/12/05/ending-ocsp/>
- <https://cabforum.org/working-groups/server/baseline-requirements/requirements/>
- <https://nginx.org/en/docs/http/ngx_http_ssl_module.html>
- <https://caddyserver.com/docs/automatic-https>
- <https://hstspreload.org/>
