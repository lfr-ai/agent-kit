# Form acceptance and recovery contract

- Task, receiving API and success evidence: {{route, contract, confirmed outcome}}
- Existing form implementation/test runner: {{tool or native form}}
- Pending edit/cancel policy: {{allowed edits, draft revision, abort meaning}}
- Duplicate and ambiguous-outcome policy: {{server guarantee or explicit limit}}

## Field map

| Field | Type/required/limits | Normalization and dependencies | Label/hint/error association | Server error key |
| --- | --- | --- | --- | --- |
| {{field}} | {{contract}} | {{rules or none}} | {{association}} | {{key}} |

## Acceptance sequences

| Given / action | Expected behavior | Test/manual evidence |
| --- | --- | --- |
| Valid draft / submit by Enter | One request; meaningful pending and confirmed success | {{result}} |
| Invalid or boundary value / submit | Correction text, associated error, intentional focus | {{result}} |
| Known and unknown server field errors | Known errors map; unknown error remains in summary | {{result}} |
| Double activation during pending | No duplicate in-flight command; feedback accessible | {{result}} |
| Rejected request / correct and retry | Draft retained, stale errors cleared, retry usable | {{result}} |
| Timeout with possibly committed request | Honest uncertainty; contract-backed lookup/retry | {{result or server limitation}} |
| New edits or navigation before old response | Old completion cannot erase new draft or hijack focus | {{result}} |

## Evidence and closure

- Synthetic fixture/reset: {{setup and cleanup; no personal input}}
- Exact focused validation/component checks: {{commands, results}}
- Browser/input-method checks: {{keyboard, native validation/autofill/composition}}
- Unverified cases: {{environment or server prerequisites}}
- Recovery action and owner: {{retry/correct/check outcome, remaining risk}}
