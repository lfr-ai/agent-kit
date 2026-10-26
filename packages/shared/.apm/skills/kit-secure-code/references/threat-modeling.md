# Threat modeling lite

A short, repeatable threat model finds design flaws that no linter can see.
Do it when adding an entry point, a trust boundary, a new data store or an
integration, and keep the result next to the code. Review date: 2026-10-23.

## Four questions

1. **What are we working on?** Draw the data flow: callers, entry points,
   processes, data stores, external services, and the trust boundaries
   between them. A list is enough when a diagram would be trivial.
2. **What can go wrong?** Walk STRIDE over every flow that crosses a boundary.
3. **What are we going to do about it?** Mitigate, eliminate, transfer or
   accept, with an owner for each decision.
4. **Did we do a good enough job?** Each mitigation has a test or a check;
   accepted risks have a review date.

## STRIDE prompts

| Threat | Property violated | Ask | Typical Python control |
| --- | --- | --- | --- |
| Spoofing | authentication | Can a caller pretend to be another user or service? | verified tokens (issuer, audience, expiry), mutual TLS between services |
| Tampering | integrity | Can data be changed in transit, at rest or in a queue? | TLS, signatures, parameterized writes, no `pickle` on shared data |
| Repudiation | non-repudiation | Can someone deny an action we cannot prove? | append-only audit events with actor, time and request id |
| Information disclosure | confidentiality | Can data leak through responses, logs, errors or files? | response models, redaction, generic errors, file permissions |
| Denial of service | availability | Can input exhaust CPU, memory, connections or disk? | size limits, timeouts, rate limits, bounded regular expressions |
| Elevation of privilege | authorization | Can a caller reach an action or object beyond their rights? | deny by default, per-object checks, least-privilege identities |

## Exposure decides depth

| Exposure | Depth |
| --- | --- |
| Internal tool run by trusted operators on their own data | a paragraph: inputs, files touched, subprocesses, credentials used |
| Internal service reachable by other systems | the worksheet for each entry point; assume other systems can be compromised |
| Service reachable from the internet or by untrusted tenants | the worksheet, abuse cases as tests, review by a second person |

"Internal" is a property of the network today, not a guarantee; record the
assumption so a later exposure change triggers a new review.

## Failure modes

- A model written once and never updated after the design changed.
- Threats listed without an owner, test or decision.
- Treating authentication as authorization: a valid token does not grant
  access to every object.
- Trusting data from "our own" queue, cache or database without validation.

## Verification

- Every boundary-crossing flow has at least one STRIDE row.
- Every mitigation links to a test, a configuration check or a code location.
- Every accepted risk has an owner and a review date.

Use the [threat model worksheet](../assets/threat-model.md.template).

## Primary sources

- [Threat Modeling Manifesto](https://www.threatmodelingmanifesto.org/)
- OWASP, [Threat Modeling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html)
- Microsoft, [Threat modeling: STRIDE](https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats)
- OWASP, [Abuse Case Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Abuse_Case_Cheat_Sheet.html)
