---
description: Design or review rate limits across edge, gateway, and application with a shared store, failure policy, and tests.
argument-hint: What to protect and from whom, e.g. "login attempts per account and per address"
agent: agent
---

# Design a rate limit

Enforce each limit once, in the outermost layer that knows the key it needs,
with a shared counter, an explicit failure policy, and predictable responses.

## Input

- The user-supplied argument names the resource and the abuse or cost to
  control. Ask for expected traffic, burst tolerance, and who may be limited
  when they are not stated.

## Procedure

1. Load [kit-fastapi-service](../skills/kit-fastapi-service/SKILL.md) and read
   its [rate-limiting reference](../skills/kit-fastapi-service/references/rate-limiting.md).
2. Classify each limit by the key it needs: connection or address limits
   belong at the edge (`kit-edge-networking`), consumer and subscription
   quotas at the API gateway (`kit-api-gateway`), and per-user, per-tenant, or
   cost-based business limits in the application.
3. For each application limit, record the key, rate, burst, window, affected
   routes, exemptions such as health probes, and the expected legitimate peak.
4. Key by the authenticated subject when one exists; use the client address
   only after the proxy-trust rules make it the real client address.
5. Use a shared store for every limit that must hold across workers or
   replicas; the per-process store is only for development and tests.
6. Choose and document the failure policy when the store is unavailable:
   fail open for availability-sensitive routes, fail closed for
   abuse-sensitive routes such as login or expensive generation.
7. Return `429` problem details with `Retry-After`; add the draft `RateLimit`
   headers only behind a setting and label them as a draft.
8. Write tests first with a fake clock: under the limit, at the limit, burst,
   window reset, per-key isolation, exempt paths, store failure in both
   policies, and the shared-store contract against a real server.
9. Emit allowed, limited, and store-error metrics per policy, and alert on
   sustained limiting of legitimate clients.
10. Run the service tests and the project completion gate.

## Acceptance gates

- [ ] Every limit has exactly one owning layer and a documented key.
- [ ] Limits that protect shared resources use a shared store.
- [ ] The failure policy is explicit per policy and tested.
- [ ] Limited responses are `429` problem details with `Retry-After`.
- [ ] Health probes and internal traffic are exempt by design.

## Output

A table of limits (layer, key, rate, burst, routes, failure policy), files
changed, and the commands run with results.
