---
name: kit-api-gateway
description: Use when adding or reviewing an API gateway or API management policies, products, and versions.
license: MIT
---

# Put an API behind a governed gateway

A gateway owns consumers, keys, plans, quotas, coarse token checks, and
policy-as-code in front of services. It does not replace the edge
(`kit-edge-networking`), the service's own authentication and authorization
(`kit-auth`, `kit-fastapi-service`), the HTTP contract (`kit-api-contracts`),
or a model gateway (`kit-llm-gateway`). Azure API Management is the deepest
worked example; [cloud equivalents](references/cloud-equivalents.md) maps the
same capabilities to Amazon API Gateway, Google Cloud API Gateway and Apigee,
and Kubernetes Gateway API implementations.

## Procedure

1. Decide whether a gateway is needed and which one, with the
   [decision guide](references/decision-guide.md): name the consumers and the
   needs it serves, fill the edge/gateway/service responsibility table, and
   choose Azure API Management (tier from the current feature matrix), Amazon
   API Gateway (REST, HTTP, or WebSocket API type), Google Cloud API Gateway
   or Apigee, a Kubernetes Gateway API implementation, or another product,
   using the [capability matrix](references/cloud-equivalents.md). Record the
   verification date. Do not start new clusters on Ingress NGINX (retired
   after March 2026).
2. Model the objects with [API Management concepts](references/apim-concepts.md):
   one instance per environment, one version set per API family, one API per
   version imported from the contract owner's OpenAPI document, products as
   plans, Key Vault-backed named values for secrets, and backend entities with
   circuit breakers. For clusters, follow
   [Kubernetes Gateway API](references/kubernetes-gateway.md); for AWS or
   Google Cloud, map each concept with the
   [cloud equivalents](references/cloud-equivalents.md) table and start from
   the [AWS HTTP API](assets/aws/api-gateway-http.tf.template) or
   [Google Cloud API Gateway](assets/gcp/api-gateway.tf.template) Terraform
   template. Keep the OpenAPI contract as the single source and generate
   per-platform configuration from it.
3. Lay out the repository per [APIOps](references/apiops.md) and adapt the
   templates rather than writing from memory:
   [main.bicep](assets/bicep/main.bicep.template),
   [apim.bicep](assets/bicep/apim.bicep.template),
   [api.bicep](assets/bicep/api.bicep.template), and
   [parameters](assets/bicep/main.bicepparam.template).
4. Write policies per [policies](references/policies.md), starting from the
   [global](assets/policies/global.xml.template),
   [API](assets/policies/api.xml.template), and
   [model API](assets/policies/ai-api.xml.template) templates:
   - `<base />` in every section below global scope;
   - explicit CORS origins;
   - `validate-jwt` (or `validate-azure-ad-token`) with issuer, audience, and
     required scopes;
   - `rate-limit-by-key` and `quota-by-key` keyed on the consumer, not on a
     proxy address;
   - contract validation in `detect` first, then `prevent`;
   - `set-backend-service` to a backend with a circuit breaker and managed
     identity toward the service;
   - one global `on-error` handler that renders `application/problem+json`
     with a correlation ID.
5. Keep every secret in Key Vault-backed named values; no literal keys,
   tokens, or passwords in XML, parameter files, or pipeline variables.
6. Gate policies with [check_apim_policy.py](assets/check_apim_policy.py):

   ```text
   python check_apim_policy.py --require-auth --require-quota apim/policies
   python check_apim_policy.py --self-test
   ```

   It prints `path:line: [rule] message`, exits 0 when clean, 1 with findings,
   and 2 for unreadable or malformed XML. It parses only local, trusted files
   with the stdlib expat parser and rejects any `DOCTYPE`. Name fragments that
   carry limits or authentication with `--limit-fragment` and
   `--auth-fragment`; skip a rule only with `--disable RULE` and a written
   reason.
7. Gate the contract: compare the candidate OpenAPI description with the
   released one using the breaking-change tool from `kit-api-contracts`; a
   breaking change ships as a new version with a published deprecation date.
8. Secure and operate per [security and operations](references/security-and-operations.md):
   service-side token validation stays on (defense in depth), backends accept
   only gateway traffic, the WAF sits at the edge, the gateway is locked to the
   edge, telemetry uses managed identity with sampling and no bodies, and
   SLOs, alerts, scale units, disaster recovery, and cost are written down.
9. Deliver with the [APIOps workflow](assets/github/apiops.yml.template):
   pull request gates without credentials, what-if per environment with a
   read-only identity, approved deployment of the same commit from dev to
   prod through OIDC, and a smoke test that an anonymous call is rejected.
   Replace every `PIN_FULL_COMMIT_SHA` before use.
10. For Kubernetes, adapt the [Gateway](assets/k8s/api-gateway.yaml.template),
    [HTTPRoute](assets/k8s/api-httproute.yaml.template), and implementation
    [SecurityPolicy](assets/k8s/security-policy.yaml.template) templates;
    use only fields that the implementation's conformance report supports.
11. Record evidence in the [gateway review worksheet](assets/gateway-review.md.template)
    and hand deployment to the pipeline; never change shared environments
    in the portal.

## Acceptance gates

- A written decision names the consumers, the responsibility split per
  concern, the chosen product and tier, and the verification date.
- Every API is imported from the contract owner's OpenAPI document; the
  breaking-change gate passes or the change is a new version.
- `check_apim_policy.py --require-auth` (plus `--require-quota` for
  external products) reports no findings, or each disabled rule has a reason.
- Every section below global scope has `<base />`; CORS lists explicit
  origins; limits key on consumer identity; errors are problem documents
  without internal detail.
- No secret appears in policy XML, Bicep, parameter files, or pipeline
  variables; Key Vault references are unversioned.
- The service still validates tokens and authorizes objects; backends reject
  traffic that bypasses the gateway.
- Bicep builds, lints, and what-if runs per environment; production deployment
  needs an approval and runs the same commit as dev.
- Logging excludes bodies and credentials; sampling, alerts, SLOs, scale, DR,
  and cost are recorded in the worksheet.

## Resources

| Resource | Use |
| --- | --- |
| [decision-guide.md](references/decision-guide.md) | Need, responsibility split, product and tier choice |
| [apim-concepts.md](references/apim-concepts.md) | APIs, products, keys, versions, revisions, named values, backends |
| [policies.md](references/policies.md) | Scopes, auth, limits, caching, CORS, validation, AI policies, errors |
| [apiops.md](references/apiops.md) | Repository layout, gates, promotion, drift |
| [security-and-operations.md](references/security-and-operations.md) | Defense in depth, mTLS, network, telemetry, SLOs, scale, DR, cost |
| [kubernetes-gateway.md](references/kubernetes-gateway.md) | API routes and auth/limit policy attachment on a Gateway API implementation |
| [cloud-equivalents.md](references/cloud-equivalents.md) | Capability matrix for Azure, AWS, Google Cloud, Kubernetes; portability |
| [api-gateway-http.tf](assets/aws/api-gateway-http.tf.template) | AWS HTTP API: JWT authorizer, stage throttling, access logs |
| [api-gateway.tf](assets/gcp/api-gateway.tf.template) | Google Cloud API Gateway from an OpenAPI document |
| [check_apim_policy.py](assets/check_apim_policy.py) | Stdlib policy checker with `--self-test` |

## Out of scope

Static checks and what-if do not prove runtime behavior. Verify token
rejection, limits, CORS preflight, error bodies, and failover against a
non-production instance before rollout. Edge TLS and WAF are
`kit-edge-networking`; delivery strategy is `kit-delivery-pipelines`; workflow
hardening is `kit-ci-review`.
