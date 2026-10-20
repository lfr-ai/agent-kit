---
description: Add an HTTP endpoint end to end with a validated contract, a typed service behind ports, stable error mapping, tests, and a schema diff.
argument-hint: Endpoint to add, e.g. "GET /invoices/{id} returns one invoice"
agent: agent
---

# Add an HTTP endpoint

Deliver one endpoint whose wire contract, behavior, and failure modes are
explicit and tested.

## Input

- The user-supplied argument describes the method, path, and outcome. Ask for
  the success response, error cases, and authorization rule if they are not
  stated and cannot be inferred from neighboring endpoints.

## Procedure

1. Load [kit-api-contracts](../skills/kit-api-contracts/SKILL.md) for the wire
   contract and [kit-python-service](../skills/kit-python-service/SKILL.md) for
   the implementation. Apply the shared `kit-test-first` skill for the test
   loop when it is installed.
2. Read two neighboring endpoints and copy their routing, dependency, error,
   and pagination conventions. Record the current published schema.
3. Write the contract first: request parameters and body, response body,
   status codes, headers, error format, idempotency, and pagination. Define
   missing, null, malformed, and out-of-range input behavior separately.
4. Model request and response schemas at the transport edge (see
   [kit-pydantic-v2](../skills/kit-pydantic-v2/SKILL.md) when the project uses
   Pydantic). Never return persistence or domain objects directly.
5. Write failing tests through the HTTP boundary: success, validation error,
   unauthorized, forbidden, not found, and conflict where relevant.
6. Implement a use case in the application layer that depends on ports. Keep
   the handler thin: parse, authorize, call the use case, map the result.
7. Map domain failures to stable public errors without stack traces, provider
   messages, or internal identifiers.
8. Wire adapters only in the composition root.
9. Regenerate the schema and compare it with the recorded one. Confirm the
   change is additive or document the migration for clients.
10. Update API examples and the changelog when clients can observe the change.
11. Run the endpoint tests, the service tests, and the completion gate.

## Acceptance gates

- [ ] Every documented status code has a test.
- [ ] The schema diff is reviewed and additive, or a migration is documented.
- [ ] No internal fields, credentials, or personal data leak in responses.
- [ ] The handler contains no business rules.

## Output

The contract summary (table of status codes and meanings), files changed by
layer, the schema diff summary, and commands run with results.
