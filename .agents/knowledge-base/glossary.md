# Glossary

Terms as this repository uses them. Where a term names code or a file, the link
points to the owner. Architecture terms (Hexagonal Architecture, ports,
adapters, layered core) are defined in [architecture](architecture.md).

## Sources and selection

- **APM (Agent Package Manager)**: The external CLI that installs and compiles agent primitives for Copilot and
  Claude. The toolkit pins `apm-cli==0.33.0` as a development dependency and
  invokes it only through explicit, non-interactive commands.
- **Primitive**: An APM-authored unit: a skill, an instruction, or a resource inside a skill.
- **Skill**: A folder `skills/kit-<topic>/` with a `SKILL.md` (frontmatter `name`,
  `description`, `license`) holding a short procedure and acceptance gates.
  Agents choose a skill by its description and load it on demand.
- **Instruction**: A `*.instructions.md` file with an `applyTo` glob; hosts apply it
  automatically to matching files.
- **Reference, asset, template**: Resources linked from a skill. References (`references/*.md`) hold detail;
  assets (`assets/`) hold copyable material. A `*.template` asset is a file a
  consumer copies; an `assets/*.py` file is a stdlib-only runnable checker.
- **Role asset**: `skills/<skill>/assets/agents.json`, a closed-schema list of agent roles.
  Source for native role projections; not itself an active agent definition.
- **Role kind and tier**: Kind is `primary` (user-selectable) or `worker` (delegated). Tier is
  `readonly`, `implementer` or `coordinator` and determines the rendered tools.
  Only primary coordinators may name workers.
- **Bundle**: A directory with `apm.yml` and `.apm/` that the catalog declares. Kind
  `project` is this repository's root; kind `portable` is a reusable package
  under `packages/`.
- **Catalog**: [catalog.json](../../catalog.json): schema version, toolkit version, supported
  runtimes, budgets, bundles and profiles. The only selection source.
- **Profile**: A named list of bundles that may `extend` other profiles. See
  [profiles](../agentic-setup/profiles.md).
- **Feature**: A profile passed with `--feature` to add its effective bundles to a base profile.
- **Effective bundles**: The ordered, de-duplicated bundle union after resolving inheritance and
  features. Inheritance cycles are validation errors.
- **Budget**: A catalog limit checked by `agent-kit check`: `policy_lines`,
  `skill_body_lines`, `description_chars` or `profile_description_chars`.
- **Runtime (target)**: A supported host, currently `copilot` and `claude`.

## Composition and delivery

- **Composition**: Planning and writing a new package for one profile plus features and
  runtimes. Planning is pure and deterministic; writing goes through a staging
  directory and an atomic no-replace rename.
- **Composed package (candidate)**: The output directory of composition. A reviewable delivery artifact, never an
  automatic change to a consumer repository.
- **Project mode**: Composition without `--skill`: every skill of the effective bundles plus
  rendered native roles.
- **Session selection (session mode)**: Composition with one or more `--skill` IDs: only those skills, project
  instructions retained, skill-specific instructions limited to selected
  skills, native roles omitted, and missing linked resources rejected.
- **Selection report**: `.apm/selection.json` in a composed package: mode, skills, instructions,
  description and instruction character counts, and native role file count.
  Character counts are not billed-token estimates.
- **Native projection (native role rendering)**: Host-specific agent files rendered from role assets: Copilot
  `.github/agents/[subagents/]<id>.agent.md` and Claude
  `.claude/agents/[subagents/]<id>.md`, with host metadata joined to one shared body.
- **Repository selection**: [self.json](../agentic-setup/self.json): the profile, features and runtimes
  this repository renders for its own native roles.
- **Ownership ledger (native lock)**: [native-lock.json](../agentic-setup/native-lock.json): SHA-256 hashes of the
  role files this repository owns. Writes refuse to replace files whose bytes
  no longer match the ledger.
- **Advisory hook (session context)**: The `SessionStart` hook running `agent-kit context`. It reports the
  workspace and missing entry files and grants or denies nothing.
- **Opt-in MCP**: MCP integrations shipped as inactive, host-shaped examples in the editor
  skill. Active manifests and the policy allow-list stay empty until a consumer
  reviews and enables one.

## Integrity and verification

- **Provenance**: `provenance.json` in a composed package: catalog version, profile, selected
  bundles and a SHA-256 hash per file. `agent-kit provenance` compares it with
  the files on disk. It is not a signature.
- **Drift**: Any difference between recorded and actual bytes. Composition-level drift is
  reported by `agent-kit provenance` (missing, extra, altered, or native
  delivery files that differ from `apm.lock.yaml`); installed-output drift is
  reported by `apm audit --ci` with `fail_on_drift`. Audit before regenerating.
- **APM ledger**: `apm.lock.yaml`, written by APM installation. Provenance admits only its
  first-party, project-scoped deployments under known delivery roots.
- **Frozen installation**: `apm install --frozen`, reproducing delivery from the existing lock; used by
  smoke to confirm the result is stable.
- **apm-check**: `agent-kit apm-check`: provenance first, then pinned `apm policy status` and
  `apm audit --ci` with the package's policy file.
- **APM smoke**: [apm_smoke.py](../../scripts/apm_smoke.py): compose, install, compile per
  runtime, verify rosters and resource bytes, audit and reinstall frozen, in a
  disposable package with an isolated home directory.
- **Coverage**: [coverage.json](../agentic-setup/coverage.json) and `scripts.check_coverage`:
  every original capability has a replacement or a recorded exclusion, and
  replacement resources exist.
- **Resource census**: `task resources:check -- --json`: per-skill linked references, assets and
  scripts, plus Python syntax checks. Structural depth, not semantic completeness.
- **Guard**: [verify_agent_config.py](../guard/verify_agent_config.py): a facade that runs
  the canonical gates through `scripts/verify.py`; not a separate engine.
- **Source archive**: `task capabilities:build` output: a deterministic ZIP of a composed package
  and its provenance. Not a native plugin or dependency-resolved bundle.

## Ownership

- **Operator action**: Version control, remote publication, release creation, global setup and
  credential changes. Performed by an approved person, not by toolkit commands.
- **Consumer**: A repository that adopts a composed package. It owns its facts, knowledge,
  memory, secrets, MCP enablement and application checks.
