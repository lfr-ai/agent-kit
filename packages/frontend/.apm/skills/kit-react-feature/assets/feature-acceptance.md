# React feature acceptance slice

- User task and bounded files: {{task, feature owner, explicit non-goals}}
- Actual stack: {{React/version, rendering mode, router, data layer, test runner}}
- Existing primitive/neighbor reused: {{paths and contracts}}
- Synthetic fixture and reset: {{setup, teardown}}

## Ownership decisions

| Value or work | Owner | Validation/update path | Disposal/reset rule |
| --- | --- | --- | --- |
| {{remote result}} | {{query/loader/adapter}} | {{schema and invalidation}} | {{obsolete result/session change}} |
| {{URL selection}} | {{router}} | {{parameter parsing}} | {{history/navigation}} |
| {{draft/interaction}} | {{component or existing shared owner}} | {{event handler}} | {{explicit reset/key identity}} |
| {{external subscription}} | {{effect or existing integration}} | {{dependencies}} | {{cleanup}} |

## Acceptance scenarios

| State/sequence | User-visible result | Regression/manual evidence |
| --- | --- | --- |
| Initial/pending | Meaningful progress; no premature success | {{result}} |
| Valid/empty result | Correct content or actionable empty state | {{result}} |
| Rejected/malformed/denied result | Safe readable feedback and allowed next action | {{result}} |
| Fail, preserve draft, retry | Work recovers without silent input loss | {{result}} |
| Newer B completes before A | B remains displayed; no stale error | {{result}} |
| Leave/switch identity during work | No old callback, private state or focus transfer | {{result}} |
| Keyboard plus narrow/reduced-motion view | Controls, focus, feedback and layout remain usable | {{result}} |
| Strict Mode/hydration, if applicable | Cleanup works; initial markup agrees | {{result or reason absent}} |

## Handoff

- Exact component/type/lint commands and results: {{evidence}}
- Real browser/assistive-technology checks: {{environment, result or not run}}
- Compatibility recovery: {{bounded revert/repair path}}
- Remaining limits and owner: {{missing runtime/server guarantee}}
