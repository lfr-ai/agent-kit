# Azure-native service selection

Load this when an Azure design or review proposes self-hosted software, or when
choosing a managed service. Prefer the managed service with Microsoft Entra
authentication and local or shared-key auth turned off. Choose self-hosted
software only with a named trigger from the last column.

"Delivery module" names a hand-written azapi module under
`packages/delivery/infra/` in the toolkit source (Bicep and Terraform).
"None" means the kit ships no module: use a pinned Azure Verified Module or
consumer code. Selecting a service does not mean Copier wires it.

Verified against Microsoft Learn on 2026-11-11 (Sources below).

## Selection table

| Need | Azure-native service | Auth mode | Delivery module | When not to use |
| --- | --- | --- | --- | --- |
| HTTP APIs, workers, jobs | Container Apps (default) | Managed identity; registry pull with `AcrPull` | `container-apps`, `container-registry` | You need the Kubernetes API or control plane: operators or CRDs, GPU node pools, a service mesh, DaemonSets. Then use AKS with that trigger recorded |
| Event-triggered functions | Azure Functions | Managed identity | None | Long-running or always-on services; use Container Apps |
| Blob storage | Storage account | Entra only, `allowSharedKeyAccess: false` | `storage-account` for application blobs; `terraform-state` for state only. Azure Files needs separate adoption | A client that only supports account keys or service SAS |
| Document or key-value NoSQL | Cosmos DB for NoSQL | Native data-plane RBAC, `disableLocalAuth: true` | `cosmos-db` | Relational joins or transactions across many entities; use PostgreSQL |
| Graph data | Cosmos DB for NoSQL adjacency documents, or PostgreSQL with Apache AGE | As the host store | `postgresql` with `extensions = ["age"]` | Cosmos DB for Apache Gremlin is not used: its client quickstarts connect with account keys. Add a dedicated graph database only with measured evidence |
| Relational data and vectors | Azure Database for PostgreSQL flexible server | Entra only, `passwordAuth: Disabled` | `postgresql`; allowlist `vector` or `age` with the `extensions` input, then run `CREATE EXTENSION` per database | Workloads that need SQL Server features |
| Cache | Azure Managed Redis | Entra access policy assignment; access keys off | `managed-redis` | Data that must survive eviction; keep it in a database |
| Queues and topics | Service Bus | Entra, `disableLocalAuth: true` | None | Fan-out of resource or system events; use Event Grid |
| Event routing | Event Grid | Entra for publishers; managed identity for delivery | None | Ordered, transactional, or long-retention messaging; use Service Bus |
| Configuration and secrets | App Configuration with Key Vault references; Key Vault | Entra; App Configuration access keys off; Key Vault RBAC | `key-vault` (App Configuration: none) | Static build-time settings that never change per environment |
| Telemetry | Application Insights through `azure-monitor-opentelemetry` with an Entra credential; Log Analytics | Entra; `DisableLocalAuth` in non-dev stages | `application-insights` | Do not use the Container Apps managed OpenTelemetry agent: it requires Application Insights local auth, exports over gRPC only, runs as one replica, and the documented setup uses preview API versions |
| Alerts | Azure Monitor metric alerts with email or a caller-owned action group (Teams via an operator-owned integration) | Managed by Azure Monitor | `container-apps-alerts` | Alerts without an owner or a destination; explicit opt-out is dev/test-only |
| Subscription auditing | Selected Activity Log export plus Service Health and access/policy alerts; once per subscription, not per app | Diagnostic setting to existing Log Analytics | `audit-logs` | An existing platform export already owns these categories; excludes Entra/data-plane/business logs and is not compliance certification |
| API gateway for LLM traffic | API Management with `llm-token-limit` and token metrics | Callers present Entra tokens (required in production) | `api-management` | Internal calls between services in one Container Apps environment |
| Public edge | Front Door with a WAF policy, or Application Gateway; API Management for API policy (row above stays) | Private Link origin where the origin supports it | None: the kit ships no edge module; see the `kit-edge-networking` skill | Private-only workloads |
| Models and agents | Microsoft Foundry | Entra, `disableLocalAuth: true` | `ai-foundry` | No exception for hosted models; local models only for offline tests |
| Search and retrieval | Azure AI Search: hybrid query with built-in Reciprocal Rank Fusion, semantic ranker, agentic retrieval | Entra, `disableLocalAuth: true` | `ai-search` (semantic ranker on in production) | Do not hand-roll fusion or a self-corrective retrieval loop when these meet the recall target. Agentic retrieval is GA only for the documented source types and minimal, extractive retrieval; query planning and answer synthesis are preview |
| OCR and document layout | Document Intelligence | Entra, `disableLocalAuth: true` | `document-intelligence` | Plain text sources that need no extraction |
| Workload identity | Managed identity | No secrets | Built into each module | No exception |
| CI deployment identity | OIDC workload identity federation | Federated credential that pins the exact subject | Delivery deploy workflows | Long-lived client secrets are never the fallback |

## Review checks

- Every data-plane resource disables local or key auth, or the review records
  why the client cannot use Entra.
- AKS, self-hosted databases, or self-hosted brokers name the trigger from the
  table, an owner, and the operating cost.
- Retrieval designs on Azure use AI Search ranking before custom fusion or
  corrective loops; graph stores beyond AGE or NoSQL adjacency need evidence.

## Sources

- <https://learn.microsoft.com/azure/container-apps/compare-options>
- <https://learn.microsoft.com/azure/azure-functions/functions-triggers-bindings>
- <https://learn.microsoft.com/azure/storage/common/shared-key-authorization-prevent>
- <https://learn.microsoft.com/azure/cosmos-db/how-to-connect-role-based-access-control>
- <https://learn.microsoft.com/azure/cosmos-db/gremlin/quickstart-python>
- <https://learn.microsoft.com/azure/postgresql/security/security-entra-concepts>
- <https://learn.microsoft.com/azure/postgresql/extensions/how-to-allow-extensions>
- <https://learn.microsoft.com/azure/postgresql/extensions/how-to-use-pgvector>
- <https://learn.microsoft.com/azure/postgresql/azure-ai/generative-ai-age-overview>
- <https://learn.microsoft.com/azure/redis/entra-for-authentication>
- <https://learn.microsoft.com/azure/service-bus-messaging/disable-local-authentication>
- <https://learn.microsoft.com/azure/event-grid/authenticate-with-microsoft-entra-id>
- <https://learn.microsoft.com/azure/azure-app-configuration/howto-disable-access-key-authentication>
- <https://learn.microsoft.com/azure/azure-app-configuration/use-key-vault-references-dotnet-core>
- <https://learn.microsoft.com/azure/azure-monitor/app/azure-ad-authentication>
- <https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-configuration>
- <https://learn.microsoft.com/azure/container-apps/opentelemetry-agents>
- <https://learn.microsoft.com/azure/azure-monitor/alerts/action-groups>
- <https://learn.microsoft.com/azure/azure-monitor/fundamentals/activity-log>
- <https://learn.microsoft.com/azure/api-management/llm-token-limit-policy>
- <https://learn.microsoft.com/azure/frontdoor/web-application-firewall>
- <https://learn.microsoft.com/azure/search/hybrid-search-ranking>
- <https://learn.microsoft.com/azure/search/semantic-search-overview>
- <https://learn.microsoft.com/azure/search/agentic-retrieval-overview>
- <https://learn.microsoft.com/azure/ai-services/document-intelligence/overview>
- <https://learn.microsoft.com/entra/workload-id/workload-identity-federation>
