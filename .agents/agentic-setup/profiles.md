# Profiles

The [catalog](../../catalog.json) is the authoring source for profile names,
bundle membership, inheritance and budgets. APM does not read that catalog.
The generated `profiles/` directories contain one compact meta-package manifest
per portable profile. Each manifest pins the selected source-package closure,
which lets a consumer install `backend` with one reference instead of listing
`shared` and `backend`.

For bundle technologies and rationale, see [technology coverage](technology-coverage.md)
and [design rationale](design-rationale.md).

## Profile map

| Profile | Effective bundles | Intended consumer |
| --- | --- | --- |
| shared | shared | Any repository that wants general development guidance |
| backend | shared, backend | Python services, APIs, persistence and packaging |
| frontend | shared, frontend | Accessible React and TypeScript clients |
| fullstack | shared, backend, frontend, coordination | Applications maintained across client and server |
| iac | shared, iac | Infrastructure, containers, CI and observability |
| terraform | shared, iac, terraform | Terraform or OpenTofu |
| bicep | shared, iac, bicep | Bicep and ARM on Azure |
| remote-access | shared, iac, remote-access | SSH, bastion and remote access |
| workflows | shared, workflows | Specification, code-graph, duplication and simplification workflows |
| ai | shared, backend, ai | Python applications with model clients, retrieval and evaluation |
| temporal | shared, backend, temporal | Durable workflows and replay-safe tests |
| identity | shared, identity | Entra ID, OIDC, scopes and roles |

The toolkit-only `toolkit` selection is intentionally not published as a
consumer profile.

## Consumer installation

In the **consumer repository**, add exactly the profile you chose to its own
`apm.yml`, pinned to a reviewed Agent Kit release:

```yaml
dependencies:
  apm:
    - lfr-ai/agent-kit/profiles/backend#v0.1.0
  mcp: []
```

Then use APM to install, compile and audit. Commit the consumer's manifest and
APM lockfile. See the [complete walkthrough](../../docs/setup-completeness.md)
for policy, updates, rollback and the distinction between source and consumer
repositories.

## Native role limitation

The catalog composer still resolves role assets so this repository can render
its own Copilot and Claude projections from
[self.json](self.json). Those native role files are **not** included in
generated consumer profiles. The APM smoke verifies source-package installation
and resource bytes; it does not test profile dependency resolution or claim
consumer role discovery.

## Maintainer workflow

Edit canonical capability files under `packages/*/.apm/` and profile membership
in `catalog.json`. Never edit files under `profiles/` by hand. Rebuild and check
the generated APM meta-package manifests:

```powershell
task profiles:build
task verify -- source
task verify -- profiles
task apm:smoke
```

`profiles:build` refuses to overwrite an unowned file or independently edited
generated output. The ownership ledger at
[`profile-lock.json`](profile-lock.json) records hashes for every generated
file. The regular `task verify` includes the source and package checks.

## Other checks and limits

| Check | Command | Proves |
| --- | --- | --- |
| Source budgets and metadata | `task verify -- source` | Catalog, bundle manifests, resources, policy, and profile budgets are valid |
| Generated profiles | `task verify -- profiles` | Each compact manifest and ownership hash matches the catalog |
| APM delivery | `task apm:smoke` | Source packages install, compile and replay in disposable projects; it does not test a released profile dependency closure |
| Resource depth | `uv run --locked python -m scripts.check_resources --json` | Linked references, assets and Python resource syntax |
| Inventory coverage | `uv run --locked python -m scripts.check_coverage` | Original capabilities have replacements or recorded exclusions |
| Repository-owned roles | `task verify -- roles` | Native role projections match their source and ownership ledger |

These gates do not certify behavior inside a live IDE, model or cloud session;
see [compatibility](../../docs/compatibility.md).
