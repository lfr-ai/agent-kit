# Route, parameter and history contract

- Route owner/router/version: {{registration, layout, base path}}
- Host rendering/fallback: {{SSR or client fallback; 404 policy}}
- Server authorization boundary: {{API/loader enforcement, no credentials}}
- Canonical path and compatibility: {{old links, slash/case/encoding rules}}

## Parameter decisions

| Parameter | Source/type | Accepted examples | Invalid/duplicate/unknown behavior | URL or local owner |
| --- | --- | --- | --- | --- |
| {{key}} | {{path/query, decoded type}} | {{normal/boundary/Unicode}} | {{reject/default/canonicalize}} | {{owner}} |

- Return destinations: {{permitted origin/path policy, parsed validation seam}}
- URL exclusion: {{secrets, private drafts, internal state never serialized}}

## Transition acceptance

| Starting state / action | URL and history expectation | Render/focus expectation | Evidence |
| --- | --- | --- | --- |
| Direct nested load and refresh | {{canonical route/base path}} | {{same content, valid assets}} | {{result}} |
| Invalid/repeated/malformed parameter | {{error or safe canonical replacement}} | {{no accidental resource request}} | {{result}} |
| Change filter then visit detail | {{push/replace rule}} | {{selection and title}} | {{result}} |
| Back then forward | {{entries restored, no new loop}} | {{URL/UI agreement}} | {{result}} |
| Denied or failed route | {{safe return destination}} | {{readable allowed next action}} | {{result}} |
| External/unexpected return URL | {{rejected or safe local fallback}} | {{no unsafe navigation}} | {{result}} |
| Leave during route load | {{new URL retained}} | {{no stale render/focus update}} | {{result}} |

## Verification and recovery

- Redirect applied twice settles at: {{same destination, loop test}}
- Exact parser/route test command and result: {{evidence}}
- Browser/host direct-load and keyboard check: {{environment or blocked}}
- Compatibility repair/revert path: {{affected links and owner}}
- Unsupported deployment/router cases: {{limits}}
