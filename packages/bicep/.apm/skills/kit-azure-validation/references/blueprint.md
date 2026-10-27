# Bicep blueprint index

Copy the templates into an `infra/` directory, drop the `.template` suffix,
and replace the example values (`orders`, `platform-team`, `cc-0000`).

| Template | Destination | Purpose |
| --- | --- | --- |
| [main.bicep](../assets/blueprint/main.bicep.template) | `infra/main.bicep` | Entry point: identity, storage module, tags |
| [types.bicep](../assets/blueprint/types.bicep.template) | `infra/types.bicep` | Exported environment, tag, and SKU types |
| [storage module](../assets/blueprint/modules/storage.bicep.template) | `infra/modules/storage.bicep` | Private storage with scoped role assignments |
| [base parameters](../assets/blueprint/parameters/base.bicepparam.template) | `infra/parameters/base.bicepparam` | Shared values (`using none`) |
| [dev parameters](../assets/blueprint/parameters/dev.bicepparam.template) | `infra/parameters/dev.bicepparam` | Extends base for dev |
| [prod parameters](../assets/blueprint/parameters/prod.bicepparam.template) | `infra/parameters/prod.bicepparam` | Extends base for prod |
| [bicepconfig.json](../assets/blueprint/bicepconfig.json.template) | `infra/bicepconfig.json` | Linter levels and formatting |
| [deploy script](../assets/blueprint/scripts/deploy.ps1.template) | `infra/scripts/deploy.ps1` | Build, validate, what-if, review, optional deploy |
| [deploy workflow](../assets/blueprint/github/bicep-deploy.yml.template) | `.github/workflows/bicep-deploy.yml` | OIDC preview and environment-gated deploy |
| [what-if reviewer](../assets/review_whatif.py) | `tools/review_whatif.py` | Read-only change classification |

## Adoption check

1. `az bicep build --file main.bicep` and `az bicep lint --file main.bicep`
   report no errors.
2. `az bicep build-params` succeeds for every environment file.
3. `az deployment group validate` passes against a sandbox resource group.
4. The what-if for an empty resource group shows only `Create` changes and
   the reviewer exits 0.
5. Every `PIN_FULL_COMMIT_SHA` in the workflow is replaced.

The parameter `extends` keyword requires Bicep CLI 0.44.1 or later; older
releases fail with `BCP406` unless the experimental `extendableParamFiles`
feature is enabled. On older tooling, copy the base values into each
environment file instead.

## Sources

- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/parameter-files>
- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/bicep-cli>
- <https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-github-actions>
