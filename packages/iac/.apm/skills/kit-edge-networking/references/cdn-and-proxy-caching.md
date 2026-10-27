# CDN and proxy caching

Verified against the primary sources below on 2026-10-27 (skill baseline
review 2026-10-23). Product behavior is stated as of 2026-10.

This reference configures shared caches (reverse proxy and CDN). What the
application emits (`Cache-Control`, `ETag`, `Last-Modified`, `Vary`, 304
handling) and application-level caches are owned by `kit-caching`; the edge
should honor those headers, not invent its own policy per route.

## Shared-cache rules that matter at the edge

- `Cache-Control: private` and `no-store` must not be stored by a shared
  cache; `no-cache` may be stored but must be revalidated before reuse
  (RFC 9111 section 5.2.2).
- `s-maxage` applies only to shared caches and wins over `max-age` there.
- A shared cache must not reuse a response to a request carrying
  `Authorization` unless the response explicitly allows it with `public`,
  `s-maxage`, or `must-revalidate` (RFC 9111 section 3.5).
- `Vary` lists request headers that are part of the cache key. `Vary: *`
  makes a response effectively not cacheable. Every extra varied header
  fragments the cache.
- `stale-while-revalidate` and `stale-if-error` (RFC 5861) let a cache serve
  stale content while refreshing or when the origin fails.
- `CDN-Cache-Control` (RFC 9213) targets CDNs specifically; use it only
  where your CDN documents support for it.

## Defaults differ per product

| Behavior | nginx `proxy_cache` | Azure Front Door (Standard/Premium) | Caddy | Traefik Proxy v3.7 |
| --- | --- | --- | --- | --- |
| Built in | Yes | Yes (per route, rules engine) | No: `cache-handler` module built with `xcaddy` | No response cache middleware |
| Honors origin `Cache-Control` / `Expires` | Yes (`X-Accel-Expires` first); `proxy_ignore_headers` disables | Yes with "Honor origin"; `private`, `no-cache`, `no-store` are honored even when a rule overrides duration | Module-specific | n/a |
| No caching headers from origin | Uses `proxy_cache_valid`, otherwise not cached | Caches for a random 1 to 3 days | Module-specific | n/a |
| Request with `Authorization` | **Not considered**: you must bypass explicitly | Not cached unless the response has `public`, `s-maxage`, or `must-revalidate` | Module-specific | n/a |
| Response with `Set-Cookie` | Not cached | Cacheable responses are cached and `Set-Cookie` is **stripped** | Module-specific | n/a |
| Methods | `GET`, `HEAD` (`proxy_cache_methods`) | `GET` | Module-specific | n/a |
| Validators | `Last-Modified` and `ETag` with `proxy_cache_revalidate on` | `Last-Modified` only (no `ETag`) | Module-specific | n/a |
| Purge | Commercial only (`proxy_cache_purge`); open source: delete cache files or change the key | Purge by path or wildcard; case-insensitive and query-string agnostic | Module API | n/a |

Consequences:

- Front Door caching on an API route whose responses lack
  `Cache-Control` can serve one user's data to another for days. Turn
  caching off on dynamic routes, or make the application send
  `Cache-Control: private, no-store` on every personalized response.
- nginx happily caches a response to an authenticated request when the
  origin forgets `private`. Always add `proxy_no_cache` and
  `proxy_cache_bypass` for credential-bearing requests;
  [check_nginx_config.py](../assets/check_nginx_config.py) flags cached
  locations that forward credentials without both.

## nginx proxy cache pattern

```nginx
# http context
proxy_cache_path /var/cache/nginx/edge levels=1:2 keys_zone=edge_cache:10m
                 max_size=1g inactive=60m use_temp_path=off;

# location context (static or public content only)
proxy_cache edge_cache;
proxy_cache_key $scheme$host$request_uri;
proxy_cache_lock on;                 # one request fills a missing entry
proxy_cache_lock_timeout 5s;
proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
proxy_cache_background_update on;    # refresh stale entries off the request path
proxy_cache_revalidate on;           # conditional requests to the origin
proxy_cache_valid 200 301 10m;       # fallback only when origin sends no caching headers
proxy_no_cache $http_authorization $cookie_session;
proxy_cache_bypass $http_authorization $cookie_session;
```

- `keys_zone` holds keys and metadata (about 8,000 keys per megabyte);
  `max_size` bounds the disk cache; `inactive` evicts unused entries.
- Include `$host` (or `$scheme$host`) in the key when one cache serves
  several sites; the default key uses `$proxy_host`, the upstream name.
- `proxy_cache_lock` plus `use_stale updating` and
  `background_update` prevent a stampede on the origin when a hot entry
  expires.
- Expose `$upstream_cache_status` (HIT, MISS, BYPASS, EXPIRED, STALE,
  UPDATING, REVALIDATED) in the access log. Adding it with `add_header` in
  a location drops the inherited security headers, so repeat them or log
  it instead.
- The [nginx template](../assets/nginx.conf.template) contains a working
  `/assets/` cache location.

## Never cache authenticated or personalized responses

1. Prefer caching only routes that are public by construction (static
   assets, public catalog pages). Keep caching off by default elsewhere.
2. Bypass and do not store when the request carries `Authorization`, a
   session cookie, or an API key header.
3. The application marks personalized responses `private` or `no-store`
   (owned by `kit-caching`); the edge configuration is the second line of
   defense, not the first.
4. Strip or refuse `Set-Cookie` on cached routes; a cached `Set-Cookie`
   hands one user's session to the next.
5. Test it: request a cached route with and without credentials and
   confirm the authenticated response is never a HIT and never served to
   the anonymous request.

## Purge, surrogate keys, and cache busting

- Prefer immutable, content-hashed static asset URLs
  (`app.3f9c2b.js`) with `Cache-Control: public, max-age=31536000,
  immutable` (RFC 8246), and short or `no-cache` HTML that references
  them. Deploys then need no purge.
- Surrogate keys (cache tags) let one purge call invalidate every object
  tagged with, say, `catalog-42`. They are vendor-specific headers, not an
  HTTP standard; Front Door purges by path and wildcard only, and
  open-source nginx has no purge. Design for versioned URLs and short TTLs
  instead of relying on tag purge.
- Make purge part of the deploy pipeline only for mutable URLs, and wait
  for purge completion before announcing a release
  (`kit-delivery-pipelines` owns the release steps).
- Front Door: purge is query-string agnostic, so purging `/catalog`
  removes every query variant.

## Configuration review

| Check | Evidence |
| --- | --- |
| Cache enabled only on intended routes | Route or location list |
| Cache key includes host and every varying input; excludes tracking parameters | Key definition; Front Door query-string behavior |
| Authenticated requests bypass and are not stored | Config lines plus a test with credentials |
| Origin sends explicit `Cache-Control` on every cached route | `curl -sI` output |
| Stale serving and request collapsing configured | `use_stale`, `lock`, `background_update` |
| Hit ratio and cache status observable | Access log field or `X-Cache` header |
| Purge or versioning procedure documented | Runbook entry |

## Primary sources

- <https://www.rfc-editor.org/rfc/rfc9111>
- <https://www.rfc-editor.org/rfc/rfc9213>
- <https://www.rfc-editor.org/rfc/rfc5861>
- <https://www.rfc-editor.org/rfc/rfc8246>
- <https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_cache>
- <https://learn.microsoft.com/azure/frontdoor/front-door-caching>
- <https://learn.microsoft.com/azure/frontdoor/front-door-rules-engine-actions>
- <https://learn.microsoft.com/azure/frontdoor/standard-premium/how-to-cache-purge>
- <https://github.com/caddyserver/cache-handler>
- <https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/overview/>
