---
name: kit-browser-debugging
description: Use when diagnosing a reproducible browser defect from runtime evidence without exposing user data.
license: MIT
---

# Diagnose from browser evidence

## Resources

- [Diagnosis guide](references/guide.md): baseline method and negative cases.
- [Debugging playbook](references/debugging-playbook.md): symptom-to-evidence
  table, network, React, performance, memory, automated reproduction,
  hypothesis discipline.
- [Evidence handling](references/evidence-handling.md): redaction rules, report
  fields, sharing limits.
- [Evidence record](assets/browser-evidence.md) to separate observations from
  hypotheses.
- Templates: [reproduction spec with evidence capture](assets/capture-evidence.spec.ts.template),
  [redaction helpers](assets/redact.ts.template) with
  [tests](assets/redact.test.ts.template).
- Checker: [HAR credential and body check](assets/check_har.py)
  (`FILES`, `--allow-bodies`, `--self-test`).

## Procedure

1. Read the guide; open the evidence record.
2. Record browser and version, route, viewport, build, flags, user action, and
   expected versus actual result.
3. Reproduce with the smallest synthetic fixture; never use a real user's data.
4. Capture the first relevant console exception with its source-mapped stack.
5. Check network status, response shape, redirects, CORS, cache headers, service
   workers, and failed asset requests.
6. Inspect the DOM, computed styles, focus, accessibility tree, and component
   state at the failing moment.
7. Compare a working browser or route only after recording configuration
   differences.
8. Classify the fault (client state, server response, timing, rendering,
   caching) with one hypothesis at a time before editing.
9. Encode the reproduction in an automated spec; add a regression test at the
   layer where the faulty contract is observable.
10. Retest the original sequence and nearby negative cases.
11. Redact tokens, cookies, query secrets, and personal fields; run the HAR check
    before sharing network exports.
12. Report causal evidence, fix, and unavailable checks; a local console alone
    cannot establish a production outage.

## Acceptance gates

- [ ] Environment and minimal synthetic steps are recorded.
- [ ] Observations, hypotheses, and confirmed causes are separated.
- [ ] A regression test fails before and passes after the fix.
- [ ] Shared artifacts passed redaction review and the HAR check.
