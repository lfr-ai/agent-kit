---
description: Apply to API Management, gateway policy XML, and Kubernetes Gateway API manifests.
applyTo: "**/apim/**,**/api-management/**,**/policies/*.xml,**/gateway/**/*.yaml"
---

- Keep `<base />` in every policy section below global scope so inherited policies still run.
- List explicit CORS origins; never allow `*`.
- Validate tokens at the gateway (issuer, audience, signed, unexpired) and still validate and authorize in the service.
- Key rate limits and quotas on consumer identity, not on a proxy or edge IP address.
- Reference secrets only through Key Vault-backed named values; no literal keys, tokens, or passwords.
- Import APIs from the contract owner's OpenAPI document; ship breaking changes as a new version.
- Render gateway errors as `application/problem+json` with a correlation ID and no internal detail.
- Change shared environments only through the reviewed pipeline, never in the portal.
- Use only Gateway API fields that the implementation's conformance report supports.
- Use the `kit-api-gateway` skill for procedures, templates, and the policy checker.
