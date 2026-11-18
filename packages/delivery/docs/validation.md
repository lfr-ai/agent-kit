# Offline validation

Use an already provisioned Python 3.13+ environment with the repository's pinned
PyYAML. The native checker performs no installs, network access or deployments.

From the repository root:

```powershell
python -B packages/delivery/check.py --workflow-root .github/workflows
```

Regenerate only when source contracts actually change, using the provisioned
locked environment:

```powershell
uv run --locked --no-sync python packages/delivery/check.py --write-catalog --workflow-root .github/workflows
```

Never hand-edit `catalog.json`. A parser-only fix should leave its schema-v4
render byte-for-byte unchanged; compare before regenerating. Task exposes the
same operations as `verify` and `catalog`; pass `PYTHON` and `WORKFLOW_ROOT` as
absolute paths when using
`task -t packages/delivery/Taskfile.yml`.

For a relocated package, invoke its `check.py` with an explicit `--workflow-root`
pointing to the directory containing the five reviewed canonical workflows.
Missing workflows fail both validation and catalog generation. There is no
fallback to a source checkout or package-local workflow copy.

## Checks

The checker enforces strict JSON/YAML, exact delivery source inventories, template
containment and parameter contracts, read-only permissions, immutable action
pins, the one reviewed source-bound composite action, safe shell interpolation,
Renovate approvals, local links and catalog freshness. It rejects a skipped,
unlocked or replaced Python Task gate. [Source ownership](integration.md)
defines catalog path resolution.

For the [Azure deployment](deploy.md) workflow, the checker requires:

- exact per-job grants: preflight `contents: read` and `actions: read`; plan and
  deploy `contents: read` and `id-token: write`;
- no workflow secrets;
- per-environment concurrency that never cancels;
- the reviewer check in a preflight job that has no environment;
- the plan job in `deployment: false`;
- the deploy job in the protected environment, after both earlier jobs;
- one artifact upload retained for one day;
- shared deploy steps that are identical to their preview steps.

The catalog projects the broadest job grant as the caller's required
permissions. Azure DevOps `deployment` jobs must target an environment, and
`inlineScript` is subject to the same interpolation ban as `bash`. Shell tests
run the extracted validation, configuration, Terraform and Bicep scripts against
local stubs. The reviewer check runs against a loopback HTTP stub, never
GitHub.

## Catalog input and failure contract

`build(root, workflow_root=...)` and `render(root, workflow_root=...)` read the
complete inventory before returning a catalog. `parameters(document)` accepts
an already decoded Azure template without mutating it.

| Source | Accepted catalog fields |
| --- | --- |
| Workflow inputs | A mapping of non-empty names to mappings; required `type` is `string`, `boolean` or `number`. `description` is an optional string. |
| Action inputs | A mapping of non-empty names to mappings; `description` is a required string. Inputs are implicitly strings; no `type` field is needed. |
| Workflow secrets | A mapping of non-empty names to mappings; optional string `description` and boolean `required`. |
| Azure parameters | An optional list of mappings with unique, non-empty string `name` and a supported string `type`. Descriptions are not required. |

GitHub `required` defaults to false and must be a boolean when supplied. Omitted
workflow descriptions render as `""`; malformed supplied descriptions never
fall back to empty text. An absent `default` remains absent in the catalog,
including when the native platform has an implicit runtime default. A declared
default must match its type: strings stay strings, booleans stay booleans, and
numbers must be finite integers or floats, never booleans. Empty strings, false,
zero and negative/fractional numbers are preserved without coercion.

Catalog GitHub loading uses a PyYAML safe loader with an isolated boolean
resolver: `on` remains a string key, unquoted true/false are booleans, and quoted
scalars without explicit tags remain strings. Thus `"false"` is not a boolean
default and `"1"` is not a number default. Legacy
`parse_yaml(..., workflow=True)` source-policy reads
still retain all scalars as strings; Azure reads retain safe PyYAML scalar types.
No global PyYAML resolver is modified.

Azure template types include `string`, `boolean`, `number`, `object`, and
`step`, `job`, `deployment`, `stage` with their corresponding `List` variants.
Singular structured defaults must be mappings; list variants must contain
mappings. `object` accepts JSON-compatible YAML values. Nested values must be
finite and fewer than 100 levels deep. Timestamps and other non-JSON objects
are rejected, not stringified. Optional `values` must be a list whose entries
match the declared type. `required` is derived solely from absence of `default`.

Malformed represented fields raise `DocumentError` naming the field rather than
leaking `KeyError`, `TypeError` or scalar-conversion errors. Duplicate YAML
fields/input names, duplicate Azure parameter names, aliases, unsafe tags,
syntax errors and oversized inputs fail closed; YAML decoder exceptions are
chained as causes. File access and UTF-8 errors remain `OSError` and
`UnicodeError`. Neither public builder returns partial results, and a failing
render cannot overwrite an existing catalog. Error reporting belongs to the
CLI boundary, not to individual parsing helpers.

This is catalog extraction, not a replacement for full native schemas or hosted
template expansion: job/step syntax, expression evaluation and platform
semantics remain with their native checks. See the
[workflow input contract](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_callinputs),
[action metadata contract](https://docs.github.com/en/actions/reference/workflows-and-actions/metadata-syntax#inputs)
and [Azure parameter types](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/template-parameters#parameter-data-types).

## Compatibility is not an execution pin

Schema types and compatibility ranges describe accepted shapes and supported
versions; they do not select an installed artifact. Keep compatibility
declarations such as Python `requires-python` and Terraform `required_version`
as ranges. Actual installers, resolved dependencies and artifacts need exact
reviewed versions, immutable revisions or digests (and paired archive checksums
where required). Catalog parsing must not rewrite a range into an execution
pin or treat a valid string as proof of immutable provenance. The separate pin
scanner covers nested manifests, actions and pipelines; native installer guards
enforce their execution inputs.

## Verification commands

Run the existing test tiers and scoped Python gates:

```powershell
uv run --locked --no-sync pytest -q -p no:cacheprovider tests/unit/delivery tests/integration/delivery
uv run --locked --no-sync ruff check --no-cache packages/delivery tests/unit/delivery tests/integration/delivery
uv run --locked --no-sync ruff format --check --no-cache packages/delivery tests/unit/delivery tests/integration/delivery
uv run --locked --no-sync ty check --extra-search-path packages/delivery packages/delivery tests/unit/delivery tests/integration/delivery
```

Use the repository's provisioned schema, actionlint, zizmor (`--offline`),
yamllint and Markdown gates on the canonical sources. The package Task target
`shellcheck` checks Azure inline scripts using an installed shellcheck.
Actionlint 1.7.12 does not understand the documented `$/` action syntax. Its
compatibility exception matches only this exact Python action reference and
diagnostic; native metadata schemas and both source-ownership gates still run.
Tests cover relocation, missing/duplicate sources, policy regressions and shell
failure propagation. Native IaC fixtures contain no resources, providers or
remote modules; unavailable native tools are reported as skipped tests.

## Limits

Offline checks do not certify hosted GitHub execution, Azure template expansion,
tool downloads, service permissions, remote presets, Codecov uploads, environment
protection rules or any Azure deployment.
Hosted setup can require network; consumer code and optional Terraform tests
require separate review. Retain existing required checks and approval gates.
