---
description: Add or reorder FastAPI middleware with a documented position, pure ASGI implementation, problem-details rejections, and tests.
argument-hint: Middleware to add, e.g. "rate limit per API key" or "request body size limit"
agent: agent
---

# Add FastAPI middleware

Add one middleware concern to a FastAPI service without breaking ordering,
context propagation, or the error contract.

## Input

- The user-supplied argument names the concern (correlation, access log,
  security headers, host check, CORS, rate limit, body limit, compression, or
  a custom one). Ask for limits, allowed origins or hosts, and the exempt paths
  when they are not stated and cannot be read from settings.

## Procedure

1. Load [kit-fastapi-service](../skills/kit-fastapi-service/SKILL.md) and read
   its middleware reference. Load
   [kit-auth](../skills/kit-auth/SKILL.md) when the concern depends on the
   caller's identity.
2. Read the app factory and list the current middleware from the outside in.
   Record where Starlette's server error and exception middleware sit.
3. Choose the position from the documented order and write down why
   (which rejections must carry the headers it adds, which work it must
   precede).
4. Write failing tests through the app factory: the accepted case, the
   rejected case with status, `application/problem+json` body, and contract
   headers, and one exempt path.
5. Implement it as a pure ASGI class (not `BaseHTTPMiddleware`) or configure
   the Starlette class. Put every tunable value in the HTTP settings facet
   with validation; no wildcard hosts or origins.
6. Build rejections with the shared problem builder so they carry the
   request id; never echo request content or tokens.
7. For stateful middleware (rate limits, caches), depend on a store port and
   state whether the default store is per process.
8. Install it in the factory at the chosen position and update the order
   comment.
9. Run the new tests, `check_fastapi_wiring.py` on the package, and the
   project gate.

## Acceptance gates

- [ ] The middleware position is documented in the factory and justified.
- [ ] Accepted, rejected, and exempt paths each have a test.
- [ ] Rejections are problem details with the request id and correct headers.
- [ ] Settings validation rejects unsafe values; no secrets reach logs.

## Output

The resulting middleware order (outside in), the files changed, the settings
added, and the commands run with results.
