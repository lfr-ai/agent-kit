# Provenance and import boundary

Upstream: `lfr-ai/delivery-kit`, unreleased version `0.1.0`, MIT,
Copyright (c) 2026 Delivery Kit contributors. [LICENSE](LICENSE) is retained.
The authorized import used the local staged working tree on 2026-11-05, not a
claimed upstream commit or release. No source checkout is required at runtime.

Imported/adapted source mapping (package-relative unless stated):

| Upstream | Canonical location |
| --- | --- |
| `.github/workflows/{python-ci,bun-ci,bicep-check,terraform-check}.yml` | Repository `.github/workflows/delivery-*.yml` |
| `azure-devops/extends/{python-ci,bun-ci,bicep-check,terraform-check}.yml` | Same paths |
| `azure-devops/jobs/python-task.yml` | Same path |
| `azure-devops/steps/{setup-python-uv,setup-bun,bicep-check,setup-terraform,setup-tflint,terraform-check}.yml` | Same paths |
| `default.json`, `renovate/*.json` | `renovate/`, with default moved under that directory |
| `scripts/{documents,catalog,check_ado_scripts}.py` | `delivery_tools/`, adapted to selected surfaces and package-relative paths |
| `tests/fixtures/{bicep,terraform}` | `fixtures/{bicep,terraform}` |

Adaptations: unique workflow names; corrected network/offline wording; explicit
Terraform-test risk; generic comments; default preset leaves timezone to the
consumer (Renovate defaults to UTC). No existing action SHA, installer checksum
contract, approval rule, locked-install gate or permission gate was weakened.
Catalog generation now includes inherited workflow permissions and only imported
entry points with explicit repository/package ownership and no package workflow
copies. GitHub CI omits the upstream optional Codecov upload contract; callers
own isolated OIDC upload jobs instead. Strict document parsing, shellcheck
extraction and catalog behavior have regression tests.

New package tooling, documentation and tests describe the import, not an upstream
release. Nothing was imported from private applications. Deployment/release
workflows, Azure resources, reference stacks, credentials, state, root governance,
repository caches, lockfiles and package-manager metadata were deliberately excluded.
