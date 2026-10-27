# Middleware order and templates

Reviewed 2026-10-23 against the Starlette and FastAPI middleware documentation.

## How order works

`app.add_middleware` inserts at the front of the stack: the last middleware
added is the outermost and sees the request first and the response last.
Starlette always wraps the user stack in `ServerErrorMiddleware` (outermost,
handles `Exception` handlers and 500s) and `ExceptionMiddleware` (innermost,
handles `HTTPException` and registered exception classes).

## Recommended order, outside in

| Position | Middleware | Why here |
| --- | --- | --- |
| 1 | Request id (`RequestIdMiddleware`) | Every later log line and rejection carries the identifier |
| 2 | Access log (`AccessLogMiddleware`) | Records status and duration for every outcome, including rejections |
| 3 | Security headers | Applied to rejections from the layers below too |
| 4 | `TrustedHostMiddleware` | Rejects forged `Host` headers before any work |
| 5 | `CORSMiddleware` | Answers preflight and adds CORS headers to 4xx responses below it |
| 6 | Rate limit | Rejects floods before body reading and handlers |
| 7 | Body size limit | Rejects large bodies before parsing |
| 8 | `GZipMiddleware` | Compresses only application responses |

[app.py.template](../assets/app.py.template) installs exactly this order.
Responses produced by `ServerErrorMiddleware` (unhandled 500s) bypass the user
stack, so they carry no CORS or security headers; keep expected failures as
`ServiceError` subclasses so `ExceptionMiddleware` renders them inside the stack.

## Templates

- [middleware.py.template](../assets/middleware.py.template): request id with a
  `ContextVar`, access log, security headers, body size limit.
- [rate_limit.py.template](../assets/rate_limit.py.template): rate limiter
  middleware and per-subject dependency over a `RateLimitStore` port, with
  route policies, failure modes, and an in-memory fixed-window store; the
  Redis store and algorithms are in [rate limiting](rate-limiting.md).
- [problems.py.template](../assets/problems.py.template): the problem response
  every middleware rejection uses.

Write middleware as pure ASGI classes. `BaseHTTPMiddleware` buffers
`call_next`, has historically broken `ContextVar` propagation and background
tasks, and cannot change the `receive` channel cleanly.

## Rules per middleware

- Request id: accept an incoming `X-Request-ID` only when it matches a strict
  pattern and length; otherwise generate one. Echo it in the response. Prefer
  W3C `traceparent` when a tracing system is present and keep `X-Request-ID`
  for humans.
- Access log: method, path without query string, status, duration, request id.
  Never headers, cookies, query strings, bodies, or tokens. Log one line per
  request; let the server log tracebacks.
- CORS: list explicit origins (scheme, host, optional port; no path or
  trailing slash). `allow_credentials=True` with `allow_origins=["*"]` makes
  Starlette reflect any requesting origin; the checker reports it. List allowed
  methods and headers; expose only headers clients read.
- GZip: set `minimum_size` (about 1 KB) so tiny bodies are not compressed;
  do not compress responses that mix secrets with attacker-controlled text
  (BREACH-style side channels).
- TrustedHost: explicit host names, never `*`; include the test client host
  (`testserver`) only in test settings.
- Body size: check `Content-Length` and count streamed chunks; raise an
  `HTTPException` subclass from `receive` so FastAPI does not turn it into a
  generic 400. Reverse proxies should enforce the same or a lower limit.
- Rate limit: before authentication key by client address as resolved by the
  server's proxy-header settings; key by verified subject in the
  `SubjectRateLimit` dependency. Exempt health probes. Return 429 problem
  details with `Retry-After`. Use a shared store when more than one worker or
  replica serves traffic and set the failure mode explicitly; see
  [rate limiting](rate-limiting.md).
- Security headers: `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`,
  `Cache-Control: no-store` for authenticated data,
  `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` for JSON,
  and `Strict-Transport-Security` only when every client reaches the service
  over HTTPS. Interactive docs need a looser policy or must be disabled.

## Primary sources

- [Starlette: Middleware](https://starlette.dev/middleware/)
- [FastAPI: Advanced middleware](https://fastapi.tiangolo.com/advanced/middleware/)
- [FastAPI: CORS](https://fastapi.tiangolo.com/tutorial/cors/)
- [ASGI specification: HTTP connection scope](https://asgi.readthedocs.io/en/latest/specs/www.html)
- [RFC 6585 section 4: 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html#section-4)
- [RFC 9110 section 10.2.3: Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3)
- [IETF draft: RateLimit header fields for HTTP](https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/)
- [OWASP HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
