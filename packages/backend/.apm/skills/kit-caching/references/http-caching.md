# HTTP caching semantics produced by the application

Verified as of 2026-10-27 against RFC 9110 (HTTP Semantics), RFC 9111 (HTTP
Caching), RFC 5861 (stale content extensions), RFC 8246 (`immutable`), and
RFC 9213 (targeted cache control).

The application decides what may be cached, by whom, for how long, and how
clients revalidate. Proxies, CDNs, and API gateways enforce those headers;
their configuration is owned by `kit-edge-networking` and `kit-api-gateway`.
The [ETag helper](../assets/etag.py.template) implements the rules below.

## Always state a policy

Without `Cache-Control`, caches may apply **heuristic freshness** to
responses with heuristically cacheable status codes (for example 200, 301,
404, 410) and a `Last-Modified` date; RFC 9111 mentions 10 percent of the
time since last modification as a typical heuristic. An API that sends no
caching headers has therefore not opted out of caching. Send an explicit
`Cache-Control` on every response, including errors.

## Response directives that matter for APIs

| Directive | Meaning (RFC 9111 unless noted) | Typical use |
| --- | --- | --- |
| `no-store` | No cache may store any part of the response | Tokens, personal or sensitive data, errors |
| `no-cache` | May be stored, but must be revalidated with the origin before each reuse | Per-user data with ETags: cheap 304s, never stale |
| `private` | Shared caches must not store; the browser may | Per-user responses |
| `public` | Any cache may store, even when the response would otherwise not be storable (for example a request with `Authorization`) | Deliberately shared data only |
| `max-age=N` | Fresh for N seconds in any cache | Client freshness |
| `s-maxage=N` | Overrides `max-age` for shared caches and implies proxy revalidation once stale | CDN/proxy freshness differing from browsers |
| `must-revalidate` | Once stale, must not be served without successful revalidation | Data where stale is worse than an error |
| `stale-while-revalidate=N` (RFC 5861) | May serve stale for N seconds while revalidating in the background | Smoothing refresh latency |
| `stale-if-error=N` (RFC 5861) | May serve stale for N seconds if the origin errors | Resilience for public data |
| `immutable` (RFC 8246) | The representation will not change while fresh; skip revalidation on reload | Fingerprinted static assets |
| `CDN-Cache-Control` header (RFC 9213) | Directives targeted only at CDN caches | Separate CDN TTLs without affecting browsers |

`Expires` is ignored when `max-age` is present; `Pragma: no-cache` is a
legacy request header and not a substitute for `Cache-Control`.

## Recipes

| Response | Header |
| --- | --- |
| Personal or sensitive data (account, payment, tokens) | `Cache-Control: no-store` |
| Per-user data that may be revalidated | `Cache-Control: private, no-cache` plus `ETag` |
| Public, shared data (catalog listing) | `Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=30, stale-if-error=600` plus `ETag` |
| Versioned static asset (`app.4be2c1.js`) | `Cache-Control: public, max-age=31536000, immutable` |
| Errors (4xx/5xx) | `Cache-Control: no-store` unless a negative result is deliberately cacheable |
| Authentication and token endpoints | `Cache-Control: no-store` |
| Writes (`POST`, `PUT`, `PATCH`, `DELETE`) | `Cache-Control: no-store`; they invalidate stored GETs for the same URI in conforming caches |

Choose numbers from the consistency budget in
[decision-guide.md](decision-guide.md); the values above are illustrations.

## Never leak per-user data through shared caches

- RFC 9111 section 3.5: a shared cache must not reuse a response to a
  request carrying `Authorization` unless the response contains `public`,
  `s-maxage`, or `must-revalidate`. Adding any of these to an authenticated,
  per-user response can make it shareable. Use `private` or `no-store` and
  reserve `public`/`s-maxage` for responses that are identical for everyone.
- RFC 9111 section 7.3: `Set-Cookie` does **not** inhibit caching. A
  cacheable response that sets a session cookie can be served, cookie and
  all, to another client. Mark such responses `private` or `no-store`.
- Responses that depend on a cookie or token but are marked public are the
  most common caching security incident. The
  [ETag helper](../assets/etag.py.template) refuses to emit a shared policy
  for a request that carries `Authorization` or `Cookie` unless the caller
  explicitly asserts the response is public.

## Vary on what selects the representation

`Vary` lists request headers that change the response, so caches key on
them. Rules:

- Include `Accept-Encoding` when the response may be compressed, and
  `Accept` or `Accept-Language` when content negotiation is used.
- Do not use `Vary: Authorization` or `Vary: Cookie` to make per-user data
  "safe" in shared caches; it fragments the cache and still relies on every
  intermediary implementing it. Use `private` instead.
- `Vary: *` means the response can never be reused without revalidation.
- A 304 must repeat the `Vary` value of the corresponding 200.

## Validators and conditional requests (RFC 9110)

| Validator | Form | Comparison |
| --- | --- | --- |
| Strong `ETag` | `"4be2c1d0"` | Changes whenever the bytes change (including encoding) |
| Weak `ETag` | `W/"4be2c1d0"` | Semantically equivalent content; bytes may differ |
| `Last-Modified` | HTTP date, one-second resolution | Fallback when no ETag exists |

Server behavior for `GET` and `HEAD`:

1. If the request has `If-None-Match`, compare with **weak comparison** (the
   `W/` prefix is ignored) against the current ETag. `*` matches any current
   representation. On a match, return `304 Not Modified`.
2. A recipient must ignore `If-Modified-Since` when `If-None-Match` is
   present. Otherwise, if `If-Modified-Since` is a valid date and the
   resource has not changed since then, return 304. Evaluate it only for
   `GET` and `HEAD`.
3. A 304 has no body and must include the `ETag`, `Cache-Control`,
   `Expires`, `Vary`, `Content-Location`, and `Date` fields that a 200 would
   have carried.

For unsafe methods, `If-Match` (strong comparison) and `If-Unmodified-Since`
implement optimistic concurrency and fail with `412 Precondition Failed`;
the status code and error contract belong to `kit-api-contracts`.

### Generating ETags

- **Content hash.** Hash the exact response bytes (for example SHA-256,
  base64url, truncated) for a strong ETag. Simple and always correct, but the
  response must be rendered before you can answer 304.
- **Version-based.** Derive the ETag from a row version or `updated_at` plus
  the representation variant (`"{id}-{version}-{lang}"`). Lets the handler
  answer 304 before loading or rendering the body. Include every input that
  changes the bytes, including the representation format and API version.
- Compression middleware that changes bytes should produce a different
  strong ETag or weaken it; check what your server stack does and test it.
- Store the ETag next to the cached value in the application cache so a
  conditional request can be answered from cache without re-rendering.

## CDN and proxy integration

- Many CDNs support surrogate keys or cache tags: the origin labels a
  response with keys (for example `product-981 catalog`) and later purges
  everything with that key. The header names and purge APIs are
  vendor-specific; their configuration, credentials, and purge wiring are
  owned by `kit-edge-networking`. The application's job is to emit stable,
  documented tags.
- Purge on write in the same place where the application cache is
  invalidated, and keep TTLs as the backstop when a purge fails.
- Prefer `s-maxage` or `CDN-Cache-Control` over vendor-only headers when a
  standard header expresses the intent.

## Testing checklist

- [ ] Every endpoint sends an explicit `Cache-Control`, including errors.
- [ ] Authenticated or cookie-setting responses are `private` or `no-store`.
- [ ] `If-None-Match` with the current ETag returns 304 with no body and the
      same `ETag`, `Cache-Control`, and `Vary` as the 200.
- [ ] A changed resource returns 200 with a new ETag.
- [ ] Weak and strong forms of the same tag both produce 304 for
      `If-None-Match`; `*` produces 304 when the resource exists.
- [ ] `If-Modified-Since` is ignored when `If-None-Match` is present.
- [ ] `HEAD` returns the same validators as `GET`.

## Sources

- RFC 9110, HTTP Semantics (validators, conditional requests, 304):
  <https://www.rfc-editor.org/rfc/rfc9110.html>
- RFC 9111, HTTP Caching: <https://www.rfc-editor.org/rfc/rfc9111.html>
- RFC 5861, HTTP Cache-Control Extensions for Stale Content:
  <https://www.rfc-editor.org/rfc/rfc5861.html>
- RFC 8246, HTTP Immutable Responses:
  <https://www.rfc-editor.org/rfc/rfc8246.html>
- RFC 9213, Targeted HTTP Cache Control:
  <https://www.rfc-editor.org/rfc/rfc9213.html>
- IANA HTTP Cache Directive Registry:
  <https://www.iana.org/assignments/http-cache-directives/http-cache-directives.xhtml>
- Starlette middleware documentation: <https://starlette.dev/middleware/>
