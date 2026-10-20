# Parameters, naming, and tags

## Parameter files

- Use `.bicepparam` files. They are type-checked against the template named
  in `using '<path>'`, so a misspelled or mistyped parameter fails at build
  time instead of during deployment.
- Keep shared values in a base file declared with `using none`, and let each
  environment file inherit it with `extends '<base>.bicepparam'` and override
  only what differs. Overriding an object or array parameter replaces it
  completely; repeat required keys.
- Build parameter files in CI with `az bicep build-params` (or `bicep
  build-params`) so type errors fail before any deployment call.
- Never commit secret values. Mark secret parameters `@secure()` in the
  template and supply them with `az.getSecret()` in the parameter file (which
  resolves a Key Vault secret at deployment time) or from a pipeline secret.
  The vault must have `enabledForTemplateDeployment` set and the deploying
  identity needs permission to read the secret.
- `@secure()` parameters must not have defaults other than empty values and
  must never flow into outputs; the linter enforces both.

## Naming

- Derive names in one place from validated parameters: resource type
  abbreviation, workload, environment, region, and instance (for example
  `st<workload><env><instance>` for storage, `id-<workload>-<env>-<instance>`
  for a managed identity).
- Respect per-type rules: storage accounts allow 3-24 lowercase letters and
  digits and must be globally unique; key vaults allow 3-24 alphanumerics and
  hyphens; many names are immutable, so a naming change means replacement.
- Prefer deterministic names. `uniqueString(resourceGroup().id)` suffixes are
  stable per scope; `utcNow()` or `newGuid()` in names cause recreation on
  every deployment and are rejected by `use-stable-resource-identifiers`.

## Tags

- Define a tag type with required keys (owner, cost center) and allow extra
  keys. Merge environment and workload tags centrally with `union()`.
- Enforce required tags with Azure Policy (`Require a tag on resources`,
  `Inherit a tag from the resource group`) rather than trusting templates.
- Tags are metadata, not security boundaries; never put secrets or personal
  data in tag values.

## Review checklist

- [ ] Every environment file builds with `build-params`.
- [ ] No secret literals; secure parameters use `@secure()` and Key Vault.
- [ ] Names come from one derivation and respect per-type constraints.
- [ ] Required tags are typed and policy-enforced.

Templates: [base parameters](../assets/blueprint/parameters/base.bicepparam.template),
[dev parameters](../assets/blueprint/parameters/dev.bicepparam.template),
[prod parameters](../assets/blueprint/parameters/prod.bicepparam.template).

## Sources

- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/parameter-files>
- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/bicep-functions-parameters-file>
- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/key-vault-parameter>
- <https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/resource-naming>
- <https://learn.microsoft.com/azure/azure-resource-manager/management/resource-name-rules>
- <https://learn.microsoft.com/azure/azure-resource-manager/management/tag-resources>
