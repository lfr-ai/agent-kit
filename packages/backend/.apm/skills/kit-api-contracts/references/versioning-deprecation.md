# Versioning and deprecation

Prefer evolving one version compatibly. Introduce a new major version only for
changes that cannot be made additively, and retire old behavior with explicit,
machine-readable signals.

## Versioning strategies

| Strategy | Example | Notes |
| --- | --- | --- |
| URL path major version | `/v1/orders` | Visible, cache-friendly, easy routing; the most common choice |
| Header or media type | `Accept: application/vnd.example.v2+json` | Clean URLs; harder to test in a browser and to cache correctly |
| Query parameter | `?api-version=2026-01-01` | Date-based versions suit frequently evolving APIs |

Choose one strategy per API and document it. Version the whole API surface, not
individual fields.

## What requires a new major version

Any change in the [breaking list](compatibility-rules.md#breaking-changes) that
cannot be avoided by adding a new field, parameter, or endpoint alongside the
old one.

## Deprecation signals

1. Mark the operation, parameter, or schema property `deprecated: true` in the
   OpenAPI description, with a description pointing to the replacement.
2. Send the `Deprecation` response header (RFC 9745) on deprecated resources.
   Its value is a Structured Field date: the Unix time at which the resource
   is or will be deprecated, written with a leading `@`, for example
   `Deprecation: @1767225600`.
3. Send the `Sunset` header (RFC 8594) with the HTTP-date after which the
   resource may stop responding, for example
   `Sunset: Wed, 30 Jun 2027 23:59:59 GMT`.
4. Link to human-readable migration information with
   `Link: <https://api.example.com/docs/migrate-v2>; rel="deprecation"` and,
   optionally, `rel="sunset"`.
5. Announce the timeline in the changelog and to known consumers.

The sunset date must not be earlier than the deprecation date.

## Timeline

- Publish the replacement first; deprecate the old surface only when the
  replacement is available in production.
- Keep a deprecation window long enough for consumers to migrate; the policy is
  per API, but it must be published and honored.
- Monitor traffic to deprecated operations by client identity; contact
  remaining consumers before the sunset date.
- After sunset, return 410 Gone with a problem details body that links to the
  migration guide, rather than 404.

## Running two versions

- Keep one domain and application core; translate per version in presentation
  adapters.
- Run each version's contract tests in CI until the old version is removed.
- Remove the old adapter, tests, and documentation together.

## Sources

- [RFC 9745 - The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745.html)
- [RFC 8594 - The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594.html)
- [RFC 8288 - Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [OpenAPI Specification 3.1.1](https://spec.openapis.org/oas/v3.1.1.html)
- [Semantic Versioning 2.0.0](https://semver.org/)
- [Google AIP-185 - API versioning](https://google.aip.dev/185)
