# API gateway capabilities across clouds

Verified as of 2026-10 against the sources listed at the end. Azure API
Management is this skill's deepest worked example (see
[concepts](apim-concepts.md) and [policies](policies.md)); this reference maps
the same capabilities to Amazon API Gateway, Google Cloud API Gateway and
Apigee, and a Kubernetes Gateway API implementation. Feature tables change
often: re-check the cited comparison pages and record the date in the
[review worksheet](../assets/gateway-review.md.template).

## Products in scope

- **Azure API Management**: managed gateway, management plane, and developer
  portal; tiers Consumption, classic (Developer, Basic, Standard, Premium), and
  v2 (Basic v2, Standard v2, Premium v2); self-hosted gateway container.
- **Amazon API Gateway** has three API types:
  - REST APIs: the full-featured type with API keys, usage plans, per-client
    throttling, request validation, caching, AWS WAF, private endpoints,
    canary deployments, and a developer portal.
  - HTTP APIs: lower-cost and minimal. AWS's comparison lists no API keys, no
    per-client rate limiting or usage throttling (so no usage plans), no
    caching, no request validation, no WAF, no private endpoint type, and no
    body transformation; HTTP APIs add native JWT authorizers and automatic
    deployments.
  - WebSocket APIs: two-way messaging routed by a route selection expression,
    with a Lambda (or IAM) authorizer on the `$connect` route.
- **Google Cloud API Gateway**: a managed gateway for Google Cloud backends
  configured by an OpenAPI document (2.0, 3.0.x, or 3.1.x) with `x-google-*`
  extensions. API keys identify the calling Google Cloud project; quotas are
  defined per API in the API config. It also offers model routing for
  OpenAI-compatible requests to Agent Platform models (check the feature's
  launch stage).
- **Apigee** (the Google Cloud-hosted offering, formerly marketed as Apigee X)
  and **Apigee hybrid** (runtime on customer-managed Kubernetes, management
  plane in Google Cloud): full API management with API proxies, policies,
  API products, developer apps, portals, analytics, and AI policies such as
  `LLMTokenQuota`. Apigee Edge is the older platform with separate
  documentation. Extensible policies require intermediate or comprehensive
  environment types and can change cost.
- **Kubernetes Gateway API** (v1.6.x standard channel; v1.6.3 latest stable at
  verification): portable routing; consumer management, auth, and limits come
  from implementation policies. Self-hosted options include Envoy Gateway
  (`SecurityPolicy`, `BackendTrafficPolicy`) and Kong (Kong Gateway plugins;
  its ingress controller implements the Gateway API). Verify edition and
  licensing terms before choosing a commercial plugin. Gateway API basics and
  Ingress NGINX migration belong to `kit-edge-networking`; see
  [Kubernetes Gateway API](kubernetes-gateway.md) for the API-gateway angle.

## Capability matrix

"Native" means configured in the product without custom code. "Custom" means a
function or plug-in you write and operate.

| Capability | Azure API Management | Amazon API Gateway | Google Cloud API Gateway | Apigee / hybrid | Gateway API + Envoy Gateway or Kong |
| --- | --- | --- | --- | --- | --- |
| Consumers and keys | Products, subscriptions, primary/secondary keys | REST: API keys attached to usage plans; HTTP and WebSocket: none (identify clients by token claims) | API keys identify the consumer project | API products, developer apps, consumer keys (`VerifyAPIKey`) | Implementation policy (Envoy API key auth, Kong key-auth plugin) |
| Rate limits | `rate-limit`, `rate-limit-by-key` (per gateway, approximate) | Token-bucket targets, best effort: REST stage, method, and per-key usage-plan throttling; HTTP stage and route throttling, not per client | Quota metrics and limits in the API config, applied to the whole API | `SpikeArrest`, `Quota` | Local (per replica) or global (shared service) rate limits |
| Quotas | `quota`, `quota-by-key` | REST: usage-plan quota per key per day, week, or month | Quota limits declared per API (see rate limits) | `Quota` per product or app | Usually not native; plugin or external service |
| JWT / OIDC validation | `validate-jwt`, `validate-azure-ad-token` | HTTP: JWT authorizer (issuer, audience, scopes); REST: Cognito or Lambda authorizer | `securityDefinitions`/`securitySchemes` with issuer, JWKS URI, audiences | `VerifyJWT`, `OAuthV2` | Envoy `SecurityPolicy` JWT providers; Kong JWT or OIDC plugins |
| Client mTLS | Client certificate validation (tier-dependent) | REST and HTTP: mTLS on custom domains with a truststore | No client-certificate setting found in the gateway docs at verification; put a load balancer in front if required | Configure at the Apigee ingress or load balancer (verify per deployment) | Gateway listener or client traffic policy |
| Response caching | `cache-lookup`/`cache-store`, built-in or external Redis-compatible | REST: stage cache; HTTP: none | None | `ResponseCache` | Implementation-specific; often none |
| Transformation | Policies (headers, body, rewrite, XML/JSON) | REST: mapping templates (body and parameters); HTTP: parameter mapping only | Backend address, path translation, and deadline through `x-google-backend` | `AssignMessage`, extension policies | `URLRewrite`, header modifiers; more via implementation |
| Request validation against the contract | `validate-content`, `validate-parameters` | REST: request validators; HTTP: none | Not documented beyond routing and authentication | `OASValidation` | Not portable |
| Versioning | Version sets (segment, header, query) and revisions | Stages and base-path mappings on custom domains; canary on REST | Separate API configs; one gateway serves one config | Proxy revisions and base paths | Separate routes per version; weighted backends |
| Developer portal | Built in (most tiers) | REST APIs (API Gateway portals) | No built-in portal; register APIs in API hub | Integrated portal and Drupal-based portal | None; separate product |
| Private networking | Private endpoints, VNet integration or injection (tier-dependent) | REST: private endpoint type; REST and HTTP: private integrations through VPC links | Backends on Google Cloud; see the networking and load-balancing pages for private patterns | VPC peering or Private Service Connect; hybrid runs in your cluster | Runs inside the cluster network |
| WAF | Front Door or Application Gateway in front | REST: AWS WAF; HTTP: put CloudFront or a load balancer with WAF in front | Cloud Armor through a load balancer | Advanced API security, Cloud Armor | Edge in front (`kit-edge-networking`) |
| AI / LLM token policies | `llm-token-limit`, `llm-emit-token-metric`, semantic cache | No token-aware policy documented; use a model gateway (`kit-llm-gateway`) | Model routing with centralized auth and quotas | `LLMTokenQuota` and other AI policies | Implementation-specific AI gateway features |
| IaC resource types | Bicep/ARM `Microsoft.ApiManagement/service/*`; Terraform `azurerm_api_management*` | Terraform `aws_api_gateway_*` (REST) and `aws_apigatewayv2_*` (HTTP, WebSocket); CloudFormation `AWS::ApiGateway::*`, `AWS::ApiGatewayV2::*` | Terraform `google_api_gateway_api`, `_api_config`, `_gateway` (google-beta provider) | Terraform `google_apigee_*` plus proxy bundles deployed by API or tooling | Kubernetes manifests (`gateway.networking.k8s.io`, implementation CRDs) |

Notable consequences:

- On AWS, "HTTP API or REST API" is a feature decision, not a price decision
  alone. Per-consumer keys, plans, caching, validation, WAF, or private
  endpoints require a REST API. An HTTP API with a JWT authorizer and stage
  throttling suits first-party clients that authenticate with tokens.
- Google Cloud API Gateway suits "OpenAPI in front of Cloud Run or functions
  with keys or JWTs". Plans, developer apps, portals, monetization, and rich
  mediation are Apigee's domain.
- A Kubernetes Gateway API implementation gives portable routing; anything in
  the "consumers, quotas, portal" rows needs another product or custom work.

## Templates

- Azure: [main.bicep](../assets/bicep/main.bicep.template) and the policy
  templates (deepest example).
- AWS HTTP API with JWT authorizer, stage throttling, and access logs:
  [api-gateway-http.tf](../assets/aws/api-gateway-http.tf.template).
- Google Cloud API Gateway from an OpenAPI document:
  [api-gateway.tf](../assets/gcp/api-gateway.tf.template).
- Kubernetes: [HTTPRoute](../assets/k8s/api-httproute.yaml.template) and the Envoy
  Gateway [SecurityPolicy](../assets/k8s/security-policy.yaml.template).

## Portability

Keep one source of truth and generate per-platform configuration from it:

1. The OpenAPI document owned by the service team (`kit-api-contracts`) is the
   contract. Paths, operations, schemas, security requirements (scopes), and
   version are defined once.
2. A small build step overlays platform specifics onto a copy of that
   document or into IaC variables: `x-amazon-apigateway-*` extensions or
   Terraform routes for AWS, `x-google-backend` and security definitions for
   Google Cloud API Gateway, an API import plus policy XML for Azure, route
   manifests for Kubernetes. The overlay never changes the contract itself.
3. Gate every platform's generated configuration with the same breaking-change
   check against the released contract, then with the platform's own linter or
   plan.
4. Keep policy intent in a platform-neutral table (who may call, scopes,
   limits per plan, timeouts, CORS origins, error format) and implement it per
   platform; review the table, not only the vendor syntax.

What does not port and must be rewritten per platform:

| Concept | Azure API Management | AWS | Google Cloud | Kubernetes |
| --- | --- | --- | --- | --- |
| Policy logic | Policy XML with C# expressions | Mapping templates (VTL), Lambda authorizers | `x-google-*` extensions; Apigee policy XML and shared flows | Implementation CRDs, plugins, filters |
| Consumer plans | Products and subscriptions | Usage plans and API keys (REST only) | Consumer projects and quotas; Apigee API products and apps | Not standard |
| Environment model | One instance per environment | Stages within one API (or separate APIs/accounts) | API configs per gateway; Apigee environments and environment groups | Namespaces and separate clusters |
| Version model | Version sets and revisions | Stages and base-path mappings | New API config per change | Separate routes |
| Error format | `on-error` renders problem details | Gateway responses (REST) | Limited control | Implementation-specific |
| Counters | Per gateway, approximate | Per stage/key, best effort | Per API | Per replica or shared service |

Rules that follow:

- Never let vendor extensions or policy expressions become the only place a
  business rule lives; business rules belong in the service.
- Expect limits, counters, and error bodies to differ slightly per platform;
  write contract tests against observable behavior (status codes, headers,
  problem types), not against vendor messages (`kit-api-testing`).
- Plan migrations as "regenerate and re-test from the contract", not as a
  translation of one vendor's configuration into another's.

## Sources

- Azure API Management tier comparison (verified 2026-10):
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-features>
- Azure API Management policy reference (verified 2026-10):
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-policies>
- Amazon API Gateway, choose between REST APIs and HTTP APIs (verified 2026-10):
  <https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html>
- Amazon API Gateway usage plans and API keys:
  <https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-usage-plans.html>
- Amazon API Gateway JWT authorizers for HTTP APIs:
  <https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html>
- Amazon API Gateway HTTP API throttling:
  <https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html>
- Amazon API Gateway WebSocket APIs:
  <https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api.html>
- Google Cloud API Gateway overview (verified 2026-10):
  <https://cloud.google.com/api-gateway/docs/about-api-gateway>
- Google Cloud API Gateway OpenAPI versions:
  <https://cloud.google.com/api-gateway/docs/openapi-overview>
- Google Cloud API Gateway API keys:
  <https://cloud.google.com/api-gateway/docs/authenticate-api-keys>
- Google Cloud API Gateway quotas:
  <https://cloud.google.com/api-gateway/docs/quotas-overview>
- Google Cloud API Gateway model routing:
  <https://cloud.google.com/api-gateway/docs/model-routing-overview>
- What is Apigee (verified 2026-10):
  <https://cloud.google.com/apigee/docs/api-platform/get-started/what-apigee>
- Apigee policy reference and policy types:
  <https://cloud.google.com/apigee/docs/api-platform/reference/policies/reference-overview-policy>
- Apigee LLMTokenQuota policy:
  <https://cloud.google.com/apigee/docs/api-platform/reference/policies/llm-token-quota-policy>
- Kubernetes Gateway API releases (v1.6.3 latest stable at verification):
  <https://github.com/kubernetes-sigs/gateway-api/releases>
- Envoy Gateway documentation: <https://gateway.envoyproxy.io/docs/>
- Kong Ingress Controller Gateway API support:
  <https://developer.konghq.com/kubernetes-ingress-controller/gateway-api/>
- Terraform AWS provider `aws_apigatewayv2_stage`:
  <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/apigatewayv2_stage>
- Terraform Google beta provider `google_api_gateway_api_config`:
  <https://registry.terraform.io/providers/hashicorp/google-beta/latest/docs/resources/api_gateway_api_config>
