# Design decisions

This index lists the toolkit's design decisions with their status and evidence.
Dated records live in [memories/decisions.md](../../memories/decisions.md); add
new durable decisions there first, then index them here. The reasoning behind
each area is expanded in the [design rationale](../agentic-setup/design-rationale.md).

Status values:

- **Accepted**: recorded and enforced by current source or tests.
- **Implemented, unrecorded**: enforced by source and documented, but without a
  dated entry in the decision log yet.
- **Superseded**: replaced by a later entry (none currently).

## Recorded decisions

| Date | Decision | Status | Enforced by |
| --- | --- | --- | --- |
| 2026-10-08 | [Canonical APM source, selected delivery](../../memories/decisions.md#2026-10-08-canonical-apm-source-selected-delivery) | Accepted | [catalog.json](../../catalog.json), `agent-kit check`, composition |
| 2026-10-08 | [Advisory hook instead of an incomplete shell filter](../../memories/decisions.md#2026-10-08-advisory-hook-instead-of-an-incomplete-shell-filter) | Accepted | `agent-kit context`, [check_native.py](../../scripts/check_native.py) |
| 2026-10-09 | [Pydantic v2 and Polars 2 stay backend opt-in](../../memories/decisions.md#2026-10-09-pydantic-v2-and-polars-2-stay-backend-opt-in) | Accepted | Backend bundle contents, data-library capability tests |
| 2026-10-09 | [Explicit session allowlists, not global runtime switches](../../memories/decisions.md#2026-10-09-explicit-session-allowlists-not-global-runtime-switches) | Accepted | `compose --skill`, session selection tests, `task apm:smoke -- --session` |
| 2026-10-09 | [Verified personal publishing identity](../../memories/decisions.md#2026-10-09-verified-personal-publishing-identity) | Accepted | `task governance:check`, `task publication:check`, `task release:check` |
| 2026-10-09 | [Completeness is an inventory contract, not a small pilot claim](../../memories/decisions.md#2026-10-09-completeness-is-an-inventory-contract-not-a-small-pilot-claim) | Accepted | [coverage.json](../agentic-setup/coverage.json), `scripts.check_coverage`, role rendering |
| 2026-10-10 | [Hexagonal Architecture is the canonical label](../../memories/decisions.md#2026-10-10-hexagonal-architecture-is-the-canonical-label) | Accepted | [architecture](architecture.md), import contracts |
| 2026-10-19 | [Keep capability resources out of application placement](../../memories/decisions.md#2026-10-19-keep-capability-resources-out-of-application-placement) | Accepted | Composed `apm.yml` compilation exclusions, [apm_smoke.py](../../scripts/apm_smoke.py) |
| 2026-10-19 | [Identity coverage is not resource-depth evidence](../../memories/decisions.md#2026-10-19-identity-coverage-is-not-resource-depth-evidence) | Accepted | [check_resources.py](../../scripts/check_resources.py), coverage regressions |

## Decisions evidenced in source

These are enforced and documented but have no dated log entry. Record one in
[memories/decisions.md](../../memories/decisions.md) before changing them.

| Decision | Status | Source of truth |
| --- | --- | --- |
| Catalog budgets bound always-on context: policy lines, skill body lines, description characters and per-profile description totals | Implemented, unrecorded | [catalog_service.py](../../src/agent_kit/application/services/catalog_service.py), [catalog.json](../../catalog.json) |
| Strict deny-by-default APM policy with unknown keys rejected | Implemented, unrecorded | [apm-policy.yml](../../apm-policy.yml), [policy](../../docs/policy.md) |
| Composition never replaces an existing destination and publishes atomically | Implemented, unrecorded | [output_adapter.py](../../src/agent_kit/infrastructure/output_adapter.py) |
| Provenance hashes every composed file and admits only first-party APM deployments | Implemented, unrecorded | [provenance_service.py](../../src/agent_kit/application/services/provenance_service.py) |
| Native role projections are rendered per host from one body with tier-bounded tools | Implemented, unrecorded | [native_delivery.py](../../src/agent_kit/application/services/native_delivery.py) |
| Repository role projections are refreshed only explicitly through an ownership ledger | Implemented, unrecorded | [render_native.py](../../scripts/render_native.py), [native-lock.json](../agentic-setup/native-lock.json) |
| MCP integrations ship as inactive examples; active manifests stay empty | Implemented, unrecorded | [compatibility](../../docs/compatibility.md), [setup walkthrough](../../docs/setup-completeness.md) |
| The pinned APM CLI version is checked at the process boundary | Implemented, unrecorded | [apm_adapter.py](../../src/agent_kit/infrastructure/apm_adapter.py), [apm_smoke.py](../../scripts/apm_smoke.py) |
| Release artifacts must match a fresh composition from the trusted checkout | Implemented, unrecorded | [check_release.py](../../scripts/check_release.py), [releasing](../../docs/releasing.md) |
| Local and CI gates share one read-only sequence | Implemented, unrecorded | [verify.py](../../scripts/verify.py), [verification](../../docs/verification.md) |

## Adding a decision

1. Reproduce or cite the evidence: a test, a script, or official documentation.
2. Add a dated `##` entry to [memories/decisions.md](../../memories/decisions.md)
   with the decision, its limits and an `Evidence:` line.
3. Add a row here with status **Accepted**; if it replaces an earlier entry,
   mark the earlier row **Superseded** and link the replacement.
4. Update the [design rationale](../agentic-setup/design-rationale.md) when the
   reasoning or rejected alternatives change.
5. Run `uv run --locked python scripts/check_docs.py` to confirm local links.
