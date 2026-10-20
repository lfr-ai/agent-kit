# Addressable routes and predictable history

## Verification prerequisites

- Identify router/version, route registration owner, nested layouts, base path,
  server rendering, deployment fallback and not-found conventions.
- Inventory path/query parameters, old links, canonicalization rules, permitted
  return destinations and server authorization. Do not invent a migration of URLs.
- Use synthetic routes/data and the existing route/browser test harness. Direct
  reload needs an actual host; an in-memory router cannot verify host fallback.

## Route quality gates

| Boundary | Required behavior |
| --- | --- |
| URL state | Refresh/share reconstructs promised selection/filter state; transient secrets and drafts stay out of the URL. |
| Parameters | Validate decoded path/query values, duplicates, allowed ranges and lengths before rendering or requests; define unknown-key handling. |
| History | Push for meaningful navigations; replace for correction or intentionally nonhistorical state. Back/forward restores UI without adding new entries. |
| Native navigation | Links expose valid destinations, support keyboard, open-in-new-tab and browser context actions; current location is communicated accessibly. |
| Pending/failure | Loading, not-found, denied, request failure and offline states are distinct and expose permitted next actions. |
| Access | Server enforces authorization; a client redirect never grants access or substitutes for an API denial. |
| Accessibility | Page title, route heading, focus and status feedback reflect navigation; avoid stealing focus on every query/filter update. |

Use the existing router's parsing and path helpers rather than manual string
concatenation. Encode parameter values once; do not decode repeatedly or allow
an encoded separator to change route ownership unexpectedly.

## Negative cases and failure modes

- Directly load and refresh a nested route under the deployment base path; confirm
  correct HTML/assets and deliberate 404 handling rather than every URL appearing
  successful.
- Supply a missing/invalid ID, repeated query key, out-of-range page, malformed
  encoding, unknown key, or Unicode value. Define reject/default/canonicalize
  behavior and avoid a request with accidental `undefined` identifiers.
- Follow a canonical redirect twice. It should settle at one destination, not
  bounce between slash/case/auth guards.
- Try external, scheme-relative, and unexpected-scheme return destinations.
  Only the contract's permitted destinations are accepted; parse before comparing
  origin/path, never trust a string prefix alone.
- Change filters, navigate to detail, then back/forward. URL and UI agree without
  feedback loops between local state and navigation effects.
- Navigate away during a route load. Ignore/cancel obsolete results and avoid
  moving focus into the old view when that request resolves.

## Recovery and verification

1. Fill the [route contract](../assets/route-contract.md) with examples and expected
   history entries before changing URL behavior.
2. For a bad parameter, choose a documented error or safe canonical value. Do not
   silently reinterpret an identifier as a different resource.
3. For auth or request failure, preserve only safe return state and offer an
   allowed next action. Keep drafts/secrets out of login-return query strings.
4. For loops, compare redirect inputs/outputs and make canonicalization
   idempotent. Repair the owning guard/layout rather than layering more redirects.
5. Run focused parser/route tests for transitions; verify direct reload and
   back/forward in an approved browser/host when available.
6. Check keyboard navigation, title, heading and focus after both success and
   error routes. Record unverified hosting and router-version behavior.

## Primary official sources

- URL parsing and encoding: <https://url.spec.whatwg.org/>
- HTML navigation and history: <https://html.spec.whatwg.org/multipage/nav-history-apis.html>
- HTML hyperlinks: <https://html.spec.whatwg.org/multipage/links.html>
- WAI page-title criterion: <https://www.w3.org/WAI/WCAG22/Understanding/page-titled.html>
