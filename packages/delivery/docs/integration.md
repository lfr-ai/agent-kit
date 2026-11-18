# Source ownership

GitHub requires reusable workflows directly in repository `.github/workflows`.
These are the sole canonical delivery workflow sources:

- `.github/workflows/delivery-python-ci.yml`
- `.github/workflows/delivery-bun-ci.yml`
- `.github/workflows/delivery-bicep-check.yml`
- `.github/workflows/delivery-terraform-check.yml`
- `.github/workflows/delivery-azure-deploy.yml` ([Azure deployment](deploy.md))

Do not duplicate them under the package. The checker requires this exact, flat
`delivery-*` inventory; unrelated repository workflows are outside its scope.
It rejects missing, unexpected, nested or escaping delivery workflow paths.

The native root verification command is:

```powershell
python -B packages/delivery/check.py --workflow-root .github/workflows
```

Invoke that checker from root verification rather than reimplementing its logic.
Python tooling resolves the `delivery_tools` namespace through the
`packages/delivery` import search path.

## Portable sources and catalog

Package files resolve from `delivery_tools.catalog.ROOT`, derived from `__file__`.
Azure `template:` paths resolve relative to the containing file and remain inside
`azure-devops`. Presets need neither workflow files nor the original source checkout.

Catalog schema 4 records GitHub workflow `path` values relative to the repository
with `sourceRoot: repository`. `githubActions` records the package-owned Python
check's native reference, input contract and package-relative path. Azure
template and Renovate paths remain package-relative.
Injected workflow directories affect reads, never the serialized canonical paths.
Relocated validation must supply all five workflows explicitly from a reviewed
source export and preserve the package's composite action. Missing, escaping,
recursive or unpinned action dependencies fail validation. It never silently
skips GitHub validation.

## Helper source is not caller source

Keep the concise, tested inline pipeline blocks unless extraction defines and
packages their complete helper-source contract. A reusable GitHub workflow's
default checkout selects the **caller**, not this repository; a path that works
in this checkout is not evidence that a remote consumer can execute it.

For a future composite-action helper, package the script beside the action and
resolve it through `github.action_path`, independently of the caller's working
directory. A reusable-workflow helper would need a separate source checkout
pinned with GitHub.com's `job.workflow_repository` and `job.workflow_sha`,
alongside an explicitly located caller checkout. These source contexts are not
available on GitHub Enterprise Server. Keep credentials disabled and test both
source and caller locations before adopting such an extraction.

An Azure template repository resource supplies templates, not a checkout of
their scripts. Extracting a helper would require an explicit repository-resource
checkout and a documented source revision/path, distinct from the caller's
workspace. Without those contracts, retain the inline implementation; moving a
block into a repository-relative script is not a portability improvement.

## Rollback

Revert workflow promotion, catalog/checker changes and affected consumer references
together; restore only one canonical source location. Keep required checks and
approval protections until replacement gates exist. Source reverts cannot undo
consumer runs, caches or external effects. The check sources manage no cloud
state; deployments, Terraform state and approvals made through the
[Azure deployment](deploy.md) path also persist after a revert.
