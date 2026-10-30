# Changelog

Notable changes, following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- **Capability selection:** `agent-kit compose --selection FILE` accepts a
  versioned selection document for project generators and CI. Session skill
  allowlists support narrower packages with recorded context footprints.
- **Infrastructure packages:** optional `terraform`, `bicep` and `remote-access`
  profiles let projects install only the tools they use.
- **Expanded guidance:** skills, instructions, prompts and templates for backend
  APIs, authentication, databases, frontend design and identity, LLM evaluation
  and agents, infrastructure, and cross-stack contracts.
- **Shared workflows:** project memory, handoffs, feedback loops, specification
  work, codebase audits and modernization. Coordinator roles can use workers
  from optional packages without requiring them in every installation.
- **Kit improvements:** `/kit-improve` helps correct reusable guidance at its
  source instead of maintaining local copies.
- **Skill evaluations:** synthetic cases and a result checker distinguish
  complete observations from missing evidence. Model runs remain explicit;
  evaluations never publish changes automatically.
- **Git guard resource:** an opt-in read-only policy for the existing tool
  guard. It does not activate hooks or grant a `kit-improve` exception.
- **Developer setup:** dedicated tool configuration, Task and VS Code templates,
  a pinned dev container, and unit, property and integration test tiers with a
  90% branch-coverage gate.
- **Checkout discovery:** Task, workspace terminals and dev-container sessions
  receive `AGENT_KIT_DIR`. Windows bootstrap registers the clone for future
  sessions; `task checkout:register` refreshes a moved clone.
- **Release tasks:** `task version:preview`, `task version:prepare` and
  `task release:build` simplify versioning and artifact checks.
  `task release:publish TAG=vX.Y.Z` requires operator confirmation and an
  existing draft. Changelog entries remain manually curated.
- **Verification:** template parsing, resource completeness, context budgets,
  Python conventions, architecture and native-delivery checks.
  `task test:matrix` runs the isolated tox environments.
- **Hosted integrations:** Codecov OIDC uploads, CodeRabbit configuration,
  CodeQL, OpenSSF Scorecard and reviewed draft releases with checksums and
  attestations. Apps, rulesets and environment protections need separate
  operator activation.
- **Consumer resources:** adoption, knowledge, runtime certification and
  opt-in MCP templates with explicit trust and removal guidance.

### Changed

- **Consumer tooling:** exported type gates use ty. Optional JavaScript MCP
  examples use Bun explicitly and still require review before activation.
- **Migration required:** Terraform, Bicep and remote-access capabilities moved
  out of `iac`. Add `--feature terraform`, `--feature bicep` or
  `--feature remote-access`, or install the matching package, to retain them.
- **IaC selection:** `kit-iac-selection` is now part of `kit-infra-review`.
- **Lower context load:** duplicate instructions are consolidated and skill
  descriptions are shorter. Existing catalog budgets are unchanged.
- **APM delivery:** on-demand skill trees are excluded from application context
  scans. Smoke tests cover every portable package in budget-compliant selections.
- **Role models:** native roles inherit the caller's model instead of pinning
  models that a host may not provide.
- **Solo-maintainer reviews:** the committed default-branch ruleset permits an
  admin bypass through pull requests only. Applying it remains an operator step.
- **Build backend updates:** `hatchling` is updated manually because Dependabot
  does not synchronize its build constraint in the lockfile.
- **Experiment configuration:** typed templates use one schema for versioned
  LLM evaluation sweeps, including model, prompt, dataset, temperature and seed.

### Fixed

- **Standalone scripts:** complete PEP 723 metadata declares empty dependency
  lists. Portable CLI tests use subprocess timeouts that clean up child processes.
- **Windows reliability:** bounded retries handle transient publication locks
  without overwriting outputs. APM output no longer depends on console encoding.
- **Launcher isolation:** APM smoke uses the toolkit launcher beside the active
  interpreter, not an unrelated executable on `PATH`.
- **Source inventory:** Git internals, installed dependencies, tool caches and
  bytecode no longer pollute composition.
- **Provenance:** noncanonical paths and unowned native prompt files are
  rejected without weakening hash or ownership checks.
- **Validation:** Markdown link checks no longer mistake Python expressions for
  links; OpenAPI path maps, recorded streams and portable templates reject
  invalid input more consistently.
- **Type coverage:** scripts, guard code and portable Python assets are included
  in type checks rather than silently skipped.
- **Markdown comments:** portable memory, handoff and debt checkers recognize
  the `--!>` closing form.
- **Edge templates:** nginx, Caddy and Traefik start HSTS at 300 seconds to match
  the documented staged rollout.
- **Dependency review:** pull-request checks use the required base/head diff;
  merge-group verification stays in the main CI matrix.

### Security

- **Dependency fix:** GitPython 3.2.1 resolves CVE-2026-114145.
- **Supply-chain checks:** bootstrap audits locks before full installation.
  Dependency audits, license checks and immutable tool pins are enforced by
  the repository gates; version updates have a 14-day cooldown.
- **Agent safeguards:** native permission rules cover package installation and
  publication. Optional guards remain defense in depth, not a sandbox.
- **Private reporting:** public issue intake directs security reports to the
  private advisory channel.

## 0.1.0 - 2026-10-08

### Added

- Original APM-first capability bundles, strict policy, profile composition,
  provenance verification, native repository adapters, and quality gates.
