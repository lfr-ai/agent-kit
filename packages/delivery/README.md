# Delivery source package

Reusable MIT [Delivery Kit](PROVENANCE.md) sources for CI checks and Azure
deployment.
This package is **not an APM bundle** or a deployment application.

| Surface | Source | Contract |
| --- | --- | --- |
| GitHub | Repository `.github/workflows/delivery-*.yml` | Four reusable CI/check workflows plus one Azure deployment workflow; no package copies |
| Python check action | [actions/python-check](actions/python-check) | One source-bound implementation shared by toolkit CI and the reusable Python workflow |
| Azure Pipelines | [azure-devops](azure-devops) | Four check extends templates plus one Azure deployment extends template, with complete job/step dependency closure |
| Azure infrastructure | [Container Apps](infra/container-apps) | One digest-based app foundation in Bicep or Terraform; staging/production use private connectivity |
| Azure network (opt-in) | [Network](infra/network) | Spoke virtual network with an apps subnet, a private-endpoint subnet, NSGs and optional private DNS zones |
| Azure cache (opt-in) | [Managed Redis](infra/managed-redis) | Entra-only Azure Managed Redis; production adds a private endpoint, lock and diagnostics, in Bicep or Terraform |
| Azure alerts (opt-in) | [Container Apps alerts](infra/container-apps-alerts) | Email or caller-owned action group (Teams/email) with restart and 5xx alerts; staging/production require a destination |
| Azure telemetry (opt-in) | [Application Insights](infra/application-insights), [audit logs](infra/audit-logs) | Application telemetry and Azure control-plane audit export have separate owners and data sources |
| Azure ingress (opt-in) | [API Management](infra/api-management) | API policy; not automatically deployed with the app |
| Azure persistence (opt-in) | [PostgreSQL](infra/postgresql) | Entra-only database server, per-database role setup and optional extension allowlist |
| Azure blobs (opt-in) | [Storage account](infra/storage-account) | Entra-only blob storage; production adds private networking, retention, diagnostics and a deletion lock |
| Azure documents (opt-in) | [Cosmos DB](infra/cosmos-db) | Entra-only Cosmos DB for NoSQL with optional database, containers and data-plane role; serverless in dev/test, production adds autoscale, zone redundancy, continuous backup, private networking, diagnostics and a deletion lock |
| Azure identity and images (opt-in) | [Key Vault](infra/key-vault), [Container Registry](infra/container-registry) | Secret references and managed-identity image access |
| Azure AI (opt-in) | [Foundry](infra/ai-foundry), [AI Search](infra/ai-search), [Document Intelligence](infra/document-intelligence) | Resource provisioning; models, indexes, permissions and ingestion remain explicit |
| Terraform backend (opt-in) | [State storage](infra/terraform-state) | Separate bootstrap ownership; a backend cannot provision itself before initialization |
| Renovate | [renovate](renovate) | Baseline, tool pins, Terraform, Bicep AVM and Azure Pipelines presets |
| Tooling | [delivery_tools](delivery_tools) | Strict YAML/JSON, generated catalog, template closure, safety checks, shellcheck extraction |
| Catalog | [catalog.json](catalog.json) | Actual inputs, defaults, required parameters, permissions and source ownership |
| Fixtures | [fixtures](fixtures) | Resource/provider-free IaC and dependency-free Bun test |

## Validate locally

Python 3.13+ and the repository's pinned PyYAML are sufficient. From the repository
root, invoke the native checker without installs or network:

```powershell
python -B packages/delivery/check.py --workflow-root .github/workflows
```

The workflow directory is required explicitly, including for relocated package
validation. Supply a directory containing all five reviewed canonical workflows;
no sibling checkout, fallback discovery or duplicate package source is used.
Azure templates and Renovate presets remain independently reusable.

See [consuming](docs/consuming.md), [source ownership](docs/integration.md) and
[validation](docs/validation.md) for contracts, catalog regeneration and tests.
Changes and upgrade notes are in the [changelog](CHANGELOG.md); releases are
tagged `delivery-vX.Y.Z` ([versions and upgrades](docs/consuming.md#versions-and-upgrades)).
Keep application settings in the application and
[IaC inputs in caller-owned environment parameters](docs/deploy.md#caller-repository-layout).
These reusable modules are opt-in sources, not proof of a deployed or fully
connected application.
For first-time CI identity setup, use the separate
[operator Azure bootstrap](docs/bootstrap.md). It plans offline unless explicitly
applied and does not use a default tenant or subscription. By default it grants
Reader only; `--access deploy` grants the constrained deployment roles.
[Identity and network](docs/identity-and-network.md) lists every identity, role,
private endpoint and production gate these compositions use.

These reusable sources do **not** make arbitrary caller code safe: callers own
their Task/script, hooks, module sources, pins, secrets and environment protections.
