# Public configuration delivery contract

Use synthetic examples only. Do not fill this worksheet with real credentials,
private hosts or complete deployment configuration.

- Actual toolchain/version and exposure rule: {{tool, public prefix/mechanism}}
- Delivery artifact/runtime source: {{build artifact or public response identity}}
- Boot owner and compatibility version: {{validation before requests}}

## Field decisions

| Public key | Purpose/type | Build/runtime | Required/default | Validation constraint | Publicness rationale |
| --- | --- | --- | --- | --- | --- |
| {{key}} | {{public purpose}} | {{delivery}} | {{required or safe default}} | {{schema, URL origin/scheme/path}} | {{why disclosure is acceptable}} |

- Excluded server-only categories: {{credentials, signing material, private hosts}}
- Unknown-key/version policy: {{reject or explicitly ignore, compatibility rule}}
- Cache contract: {{app/config pairing, validators/lifetime, approved owner}}
- Error and retry UI: {{safe key/reason, focus/status, retry prerequisite}}

## Acceptance matrix

| Fixture | Expected result | Evidence |
| --- | --- | --- |
| Valid synthetic config | Exactly the intended public settings initialize client | {{result}} |
| Required key missing/blank/wrong type | Visible safe error; zero dependent requests | {{result}} |
| Unsafe URL/credentials/unapproved origin | Validation rejects before any request | {{result}} |
| Unsupported version/unknown key | Documented compatibility behavior | {{result}} |
| HTML/malformed JSON/timeout/non-success | Load failure distinct from valid empty data | {{result}} |
| Old cached config with new app | Compatible or explicitly blocked | {{result}} |
| Delayed old attempt after retry/disposal | Cannot initialize stale client | {{result}} |

- Focused checks and exact results: {{commands or unavailable}}
- Delivered-asset inspection: {{build identity, files/maps/response scope}}
- Search scope and limits: {{local sentinel/key checks, no absence guarantee}}
- Recovery workflow/owner: {{correct public config or compatible pair rollback}}
