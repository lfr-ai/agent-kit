# Sanitized browser defect record

- Symptom and blocked user task: {{expected vs actual}}
- Build, browser/version, viewport and input method: {{environment}}
- Route and synthetic fixture: {{redacted location, setup/reset}}
- Cache/service worker/auth state: {{safe state description; no stored values}}
- Reproduction: {{numbered actions, frequency, first failing action}}

## First evidence

- Earliest relevant exception and causal stack location: {{sanitized excerpt}}
- Request contract: {{initiator, status, content type, shape, cache source}}
- DOM/layout/focus observation: {{element, visibility, active focus, tree}}
- Capture safety: {{fields removed, approved retention, local evidence location}}

## Discriminating probes

| Hypothesis | Single change | Predicted observation | Actual observation | Supported/rejected/unknown |
| --- | --- | --- | --- | --- |
| {{response contract}} | {{probe}} | {{prediction}} | {{result}} | {{decision}} |
| {{state ordering or cleanup}} | {{probe}} | {{prediction}} | {{result}} | {{decision}} |
| {{cache/layout/input}} | {{probe}} | {{prediction}} | {{result}} | {{decision}} |

## Repair verification

| Sequence | Expected contract | Evidence or blocker |
| --- | --- | --- |
| Original reproduction | Reported failure no longer occurs | {{test/manual result}} |
| Refresh or direct load | Same route works without prior navigation | {{result}} |
| Failure then retry | Readable error, usable recovery, no duplicated work | {{result}} |
| Keyboard or navigation away | Focus remains usable; abandoned work does not update view | {{result}} |

- Proven owner and causal explanation: {{evidence, not correlation}}
- Smallest repair and retained regression: {{boundary, test}}
- Limitations: {{unreproduced environments, missing maps, remaining hypotheses}}
