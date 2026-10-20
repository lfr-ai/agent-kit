# Bicep modules and Azure Verified Modules

## Module design

- A module is any `.bicep` file called with `module <symbol> '<path>' = {}`.
  It compiles to a nested deployment with its own parameters, so values
  computed at runtime in the parent (for example a principal ID) become
  deployment-time parameters inside the module. Use this to give resources
  deterministic names that depend on parent outputs.
- Keep each module focused on one capability with secure defaults (storage
  with private access, a key vault with RBAC authorization) and expose only
  the parameters consumers legitimately vary.
- Give every parameter and output a `@description`. Prefer user-defined types
  and literal unions (`'dev' | 'test' | 'prod'`) over loose strings; export
  shared types with `@export()` and `import` them where needed.
- Outputs must not carry secrets. Return resource IDs and names; let consumers
  read keys through `existing` references or, better, use Entra ID auth.
- Use the `existing` keyword to reference resources owned elsewhere instead
  of redeclaring them. Redeclaring a resource makes this template its owner
  and can reset properties it does not set.
- Prefer symbolic references (`storage.outputs.id`, `parent: account`) over
  string-built resource IDs; Bicep then infers dependencies, so explicit
  `dependsOn` is rarely needed.

## Scopes

| `targetScope` | Typical content |
| --- | --- |
| `resourceGroup` (default) | Workload resources |
| `subscription` | Resource groups, policy assignments, role assignments, budgets |
| `managementGroup` | Policy definitions and initiatives, management group RBAC |
| `tenant` | Management groups, tenant-wide settings |

Use the `scope:` property on modules to deploy into a different resource
group or subscription from one entry point, and record every scope the
deployment touches in review evidence.

## Azure Verified Modules (AVM)

AVM is the Microsoft-supported library of Bicep and Terraform modules with
consistent interfaces (diagnostics, role assignments, locks, private
endpoints, managed identities) and secure defaults.

- Reference resource modules from the public registry with an exact version:
  `br/public:avm/res/storage/storage-account:<version>`. Never omit the
  version; the `use-recent-module-versions` linter rule reports newer ones.
- Pattern modules (`avm/ptn/...`) compose several resources for a scenario;
  review them as you would any multi-resource template.
- Read the module's README for the parameter contract and its changelog
  before upgrading; AVM follows semantic versioning but pre-1.0 modules may
  change interfaces in minor versions.
- Pin and restore modules in CI with `bicep restore` so builds are
  reproducible and fail fast when the registry is unreachable.
- For private modules, publish to an Azure Container Registry with
  `az bicep publish` and add an alias in `bicepconfig.json`.

## API versions

- Pin explicit, stable API versions on every resource type. Preview versions
  are acceptable only with a recorded reason.
- The `use-recent-api-versions` rule warns when a version is older than the
  configured age. Upgrading an API version can change defaults; run what-if
  after every upgrade.

## Review checklist

- [ ] Modules have described, typed parameters and outputs with no secrets.
- [ ] Registry modules carry exact versions; private registries use aliases.
- [ ] `existing` is used for resources owned elsewhere.
- [ ] Every scope the deployment touches is recorded.
- [ ] API versions are stable and recent; upgrades re-run what-if.

Templates: [main.bicep](../assets/blueprint/main.bicep.template),
[storage module](../assets/blueprint/modules/storage.bicep.template),
[types.bicep](../assets/blueprint/types.bicep.template),
[bicepconfig.json](../assets/blueprint/bicepconfig.json.template).

## Sources

- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/modules>
- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/user-defined-data-types>
- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/bicep-import>
- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/existing-resource>
- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/best-practices>
- <https://azure.github.io/Azure-Verified-Modules/>
- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/bicep-config-modules>
- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/linter-rule-use-recent-api-versions>
