# Public configuration boundary and delivery

## Verification prerequisites

- Identify the actual build tool/framework and its version, public-variable
  exposure rules, runtime config endpoint/file if any, boot order, and cache
  policy. Prefix names differ by tool; never infer secrecy from a prefix.
- Classify each proposed value as intentionally public or server-only before
  wiring it into the client. Browser assets, source maps, HTML, runtime responses
  and devtools-visible values are readable by the user.
- Obtain only synthetic configs and existing validation/build commands. Artifact
  inspection requires a known build; source inspection alone cannot prove delivery.

## Configuration quality gates

| Decision | Required contract |
| --- | --- |
| Delivery time | Each field is build-time or runtime; changing a runtime field does not secretly require a rebuild. |
| Public schema | Narrow typed keys, schema/version policy, requiredness and safe optional defaults are declared at one boundary. |
| URL validation | Parse endpoint URLs; constrain scheme, approved origin/base path, and credential absence under the consumer's contract. |
| Failure | Missing/invalid required config blocks dependent operations with readable feedback; no fallback to page origin or an unintended host. |
| Boot | Load and validate runtime config before dependent requests; late completion after disposal cannot start abandoned work. |
| Cache/version | Config and app versions have a compatibility rule; deployment/cache behavior cannot silently pair an old schema with a new client. |
| Diagnostics | Report key names and safe reason codes, not full values, tokens, internal URLs or the complete config object. |

A public feature flag is a presentation switch, never authorization. Public
client identifiers may be legitimate only when their provider explicitly treats
them as publishable; API credentials/signing keys and private service addresses
remain server-owned. Type declarations alone do not validate a downloaded object.
If embedding JSON in HTML, use the framework's safe serialization mechanism;
raw interpolation can terminate a script element or create markup.

## Negative configurations and failure modes

- Remove a required key; provide a blank or wrong-typed value. The error identifies
  the key safely and makes no dependent request.
- Supply an unexpected URL scheme, credentials-in-URL, scheme-relative endpoint,
  or unapproved origin. Reject it under the recorded URL policy.
- Add an unknown key or unsupported schema version. Apply the documented
  reject/ignore compatibility rule; never spread arbitrary config into the app.
- Return HTML, malformed JSON, a non-success status or timeout from runtime
  loading. Do not misreport these as "empty successful configuration."
- Serve a stale config/app pairing from cache. Require a compatible pair or a
  safe incompatibility message; repeated reload is not a compatibility strategy.
- Delay config then retry or leave the startup view. Only the current valid
  attempt may initialize the client.

## Recovery and verification

1. Fill the [public configuration contract](../assets/public-config-contract.md)
   with ownership and compatibility decisions before implementation.
2. For invalid required data, block affected functionality and present a
   keyboard-reachable retry if runtime retrieval can recover. Do not default a
   security-sensitive or required value to a convenient production endpoint.
3. Correct config through its owning approved deployment workflow. Roll back to
   a known compatible app/config pair if needed; this skill does not authorize
   deployment, credential changes or cache purges.
4. Run focused boundary tests with synthetic fixtures and inspect an available
   known build/runtime response, including maps and embedded config. Search
   locally for prohibited key names and synthetic sentinels; never print secrets.
5. Report inspected artifact identity, files/scope, commands and residual limits.
   A string scan cannot prove that no encoded or unexpected secret exists.

## Primary official sources

- URL validation semantics: <https://url.spec.whatwg.org/>
- Fetch response and failure semantics: <https://fetch.spec.whatwg.org/>
- HTTP cache controls: <https://www.rfc-editor.org/rfc/rfc9111.html>
- Vite public env rules, only for Vite consumers: <https://vite.dev/guide/env-and-mode>
- Next.js public env rules, only for Next.js consumers: <https://nextjs.org/docs/app/guides/environment-variables>
