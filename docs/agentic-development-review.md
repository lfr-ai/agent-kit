# Agentic development review and improvement plan

Review date: 2026-10-28. Baseline: `e905e78`, initially clean worktree.

## Scope and decision

Review the Python toolkit, portable APM capabilities, native Claude and Copilot
adapters, development tools, review practices, CI and open-source delivery.
Compare the requested Anthropic articles with current primary documentation.
Implement relevant, evidenced defects; do not install an idealized stack.

The existing architecture does not need replacement. Its strongest properties
are explicit capability selection, one authoring source, inward dependencies,
strict input contracts, no-replace composition, provenance, read-only gates and
real APM delivery checks. The useful improvements are in failure visibility,
ownership enforcement, review evidence and installation ordering.

This is not a production certification, exhaustive proof of correctness,
penetration test, native-session benchmark or hosted-settings attestation.
Implementation and setup specialists reviewed separate scopes. Domain-specific
resource tests were sampled; the complete deterministic suite is a separate
acceptance gate. No company application, credentials or private runtime logs
were sent to external services.

## 1. Evidence model

Keep these evidence levels separate throughout adoption:

| Level | What it establishes | What it does not establish |
| --- | --- | --- |
| Primary documentation | A vendor's documented contract at review time | Support in an older installed host or pinned APM release |
| Source inspection | An actual configuration, implementation or concrete defect path | Successful execution or enforcement |
| Deterministic regression | The tested behavior, including the selected negative cases | Every filesystem, host, model or account configuration |
| Real APM smoke | Pinned installation/compilation, ownership and delivered bytes | IDE discovery, model compliance, approval prompts or MCP authentication |
| Native-session exercise | Observed behavior in the named host, harness and version | Other hosts, versions, user/plugin context or identities |
| Hosted operator check | Observed repository/app/environment controls | Enforcement from a committed JSON/YAML file alone |

Use the [verification contract](verification.md) and
[native certification worksheet](../packages/shared/.apm/skills/kit-agent-runtime/assets/certification.md.template).
Never turn missing access into a passing check.

## 2. Baseline inventory and architecture

The initial source check reported all eleven profiles valid, with unchanged
limits: 120 policy lines, 300 lines per skill body, 350 description characters
per skill and 6,500 description characters per profile.

| Profile | Selected skills | Description characters |
| --- | --- | --- |
| toolkit | 26 | 2,648 |
| shared | 22 | 2,257 |
| backend | 38 | 3,927 |
| frontend | 37 | 3,732 |
| fullstack | 55 | 5,588 |
| iac | 29 | 2,937 |
| workflows | 28 | 2,919 |
| ai | 46 | 4,793 |
| terraform | 30 | 3,034 |
| bicep | 30 | 3,028 |
| remote-access | 30 | 3,025 |

These are authored-character measurements, not token, cache, latency, cost or
model-adherence results. Re-run `uv run --locked agent-kit check --root . --json`
after selection or discovery-text changes. Do not load all profiles into every
session merely because their budgets pass.

The reviewed canonical tree contained 83 skills, 54 instructions and 45 prompt
facades. Counts are a dated snapshot, not another source of truth; the catalog,
source check and resource census remain authoritative.

### Responsibilities retained

- **Core:** concrete immutable records and ports; stdlib only.
- **Application:** validation, selection, planning and provenance interpretation.
- **Infrastructure:** filesystem capture, parsing and external process adapters.
- **Presentation/composition:** CLI diagnostics and dependency wiring.
- **Canonical capabilities:** root `.apm/` for toolkit-only guidance and the
  smallest audience package for reusable procedures.
- **Native adapters:** provider-specific tools, permissions and hook fields.
- **Consumer repositories:** actual application commands, domain knowledge,
  identities, private facts, operational checks and deployment decisions.

The [architecture contract](../.agents/knowledge-base/architecture.md) explains
why this is a ports-and-adapters toolkit, not a requirement to generate layers,
interfaces or domain objects in every consumer.

## 3. Ordered TODO and ownership

The plan deliberately favors repairs and reuse over new capability entries.
The acceptance column defines completion; implementation alone is insufficient.

| Order | Work item | Owner | Acceptance |
| --- | --- | --- | --- |
| 1 | Record baseline, contracts and generated drift before refresh | Coordinator | Exact source/drift results; existing failures retained |
| 2 | Research both requested articles and relevant current official contracts | Research worker | Verified URLs, synthesis, dates and unavailable-source caveats |
| 3 | Audit implementation and native/OSS setup independently | Read-only reviewers | Concrete scenarios, locations, severity and limits |
| 4 | Check placement, reuse, compatibility and task boundaries | Plan architect | Existing owners; no duplicate layers or widened permissions |
| 5 | Fail closed on incomplete filesystem capture and generated-selection collisions | Backend worker | Read/enumeration/collision regressions and existing valid cases pass |
| 6 | Prevent checksum target overwrite and reject incomplete distribution archives | Delivery worker | External bytes preserved; valid and invalid artifact tests pass |
| 7 | Correct YAML key identity and module-qualified template import checks | Test worker | Demonstrated false-negative and false-positive regressions pass |
| 8 | Enforce native ledger identity, unowned collisions and actual role roster | Native worker | Alias/extra-role/unowned cases fail without destructive adoption |
| 9 | Make advisory session entry non-installing and validate native switches | Native worker | No-sync contract and invocation/hook-disable mutations pass |
| 10 | Audit before CI installation and strengthen existing governance assertions | Governance worker | CI graph, ruleset and inventory mutation tests pass |
| 11 | Improve the existing review and feedback procedures | Coordinator | Read-only review, evidence, uncertainty, deduplication and bounded iteration |
| 12 | Document actual hosted protection limits, not intended guarantees | Governance worker | Bypass/tag claims match committed definitions; operator work remains explicit |
| 13 | Audit, then refresh only owned projections with pinned tools | Coordinator | Native/APM ownership and drift checks pass after refresh |
| 14 | Review integration, resolve defects and run final acceptance | Coordinator and reviewer | `task verify` and `task apm:smoke`; exact results and limitations |

Workers own disjoint files; the coordinator owns shared documentation and
generated output. Workers do not delegate, publish, change global settings or
install new services. A source change that affects a shared contract must be
tested at its consumer boundary, not only in the worker's local helper.

## 4. Concrete defects and disposition

The findings below are specific to this checkout, not requirements inferred
solely from a blog post. Regressions establish the behavior before accepting a
fix. Source locations are owning files rather than unstable line ranges.

| Priority | Finding | Source owner | Required resolution |
| --- | --- | --- | --- |
| High | Checksum generation can follow an existing destination symlink and overwrite unrelated bytes | [Release checker](../scripts/check_release.py) | Reject unsafe locations; publish completed checksum bytes safely |
| Medium | Filesystem enumeration failures can silently omit source or output subtrees | [Catalog adapter](../src/agent_kit/infrastructure/catalog_adapter.py) | Surface capture failures; never attest an incomplete census |
| Medium | Provenance can hash empty placeholder bytes after an unreadable-file failure | [Provenance service](../src/agent_kit/application/services/provenance_service.py) | Distinguish failed reads from readable empty or parse-invalid bytes |
| Medium | Generated selection metadata bypasses source-output collision checks | [Catalog service](../src/agent_kit/application/services/catalog_service.py) | Reuse collision handling before publication |
| Medium | Review evidence can be declared ready without acceptance criteria | [Review package](../packages/shared/.apm/skills/kit-agent-runtime/assets/review_package.py) | Block missing, null and empty acceptance lists |
| Medium | Lexical path-prefix checks accept `src/../outside.py` | [Review package](../packages/shared/.apm/skills/kit-agent-runtime/assets/review_package.py) | Reject traversal and non-relative paths, including rename sources |
| Medium | Native ledger aliases can cause a refresh to remove a retained role | [Native renderer](../scripts/render_native.py) | Reject noncanonical keys before any mutation |
| Medium | Identical unowned native files can be silently adopted, then removed later | [Native renderer](../scripts/render_native.py) | Refuse unowned collisions; do not infer ownership from equal bytes |
| Medium | Extra discovered native role files are absent from drift checking | [Native renderer](../scripts/render_native.py) | Compare actual roster against ownership and explicit repository exceptions |
| Medium | Session hooks can synchronize dependencies before audited bootstrap | [Native checks](../scripts/check_native.py) | Non-syncing execution; bootstrap remains explicit |
| Medium | CI dependency-consuming jobs install concurrently with their audit | [CI](../.github/workflows/ci.yml) | Make audit success a dependency, not just another final status |
| Medium | Ruleset mutations can exclude protected refs or weaken review/check requirements without gate failure | [Governance checker](../scripts/check_governance.py) | Assert the existing reviewed exclusions, rule uniqueness, counts and strictness |
| Medium | Release checks accept archives containing metadata/license but no usable package | [Release checker](../scripts/check_release.py) | Verify the existing package and entry-point contract; do not claim installation from archive shape alone |
| Low | Template imports are checked against symbols across unrelated modules | [Toolchain tests](../tests/unit/repo_guards/test_template_toolchains.py) | Resolve declared local exporting modules and symbols together |
| Low | YAML duplicate detection uses key spelling rather than decoded identity | [Structured-template tests](../tests/unit/repo_guards/test_structured_templates.py) | Reject equivalent numeric keys; preserve distinct numeric/string keys |
| Low | Existing update ecosystems, issue forms and native booleans are not fully asserted | [Governance checker](../scripts/check_governance.py), [native checks](../scripts/check_native.py) | Extend current mutation tests, not add another checker |

The review evidence probe before repair printed `empty acceptance: ()`,
`path escape accepted: True` and `gate findings: []`. The focused red run then
failed five cases covering absent acceptance and traversal on changed/renamed
paths. A normal successful command is not sufficient evidence of task acceptance.

The code/checker repairs and portable review improvements were implemented in
their existing owners. Stricter import checking also exposed three incomplete
template destination declarations; those declarations now match their example
imports rather than adding an exception to the checker.

An independent integrated review found one introduced release-validator defect:
the INI parser normalized console-script names, accepting `Agent-Kit` where the
declared command is `agent-kit`. The release worker reproduced it, retained the
negative case and preserved exact names using the parser's supported override.
All 35 release tests then passed, including refusal to checksum that artifact.

### Protection claims corrected, not silently deployed

The committed administrator PR bypass applies to the whole main ruleset, not
only self-approval. The committed release-tag definition protects mutation and
deletion but does not prohibit creation of a fresh matching tag. Native command
restrictions do not close either server-side gap.

See [GitHub setup](github-setup.md) for the actual policy and operator decisions.
If required checks must have no bypass, separate that protection from an
approval exception. If only a release identity may create tags, review creation
restriction separately from tag immutability. Do not claim either change is
active from local configuration.

## 5. Target development and review loop

The reusable owners already exist:
[planning](../packages/shared/.apm/skills/kit-change-plan/SKILL.md),
[onboarding](../packages/shared/.apm/skills/kit-context-onboarding/SKILL.md),
[delegation](../packages/shared/.apm/skills/kit-subagent-delivery/SKILL.md),
[review](../packages/shared/.apm/prompts/kit-review-change.prompt.md),
[feedback](../packages/shared/.apm/skills/kit-feedback-loop/SKILL.md) and
[verification](../packages/shared/.apm/skills/kit-verify-change/SKILL.md).

1. **Orient:** identify intent, current revision, owned paths, applicable rules
   and the nearest proving test. Inspect existing solutions before adding one.
2. **Plan proportionately:** write observable criteria, failure cases, actual
   prerequisites, a bounded iteration budget and operator-only steps.
3. **Implement one complete behavior:** reproduce a defect, retain its failing
   test, repair the cause and preserve the relevant callers.
4. **Verify deterministically:** run focused tests and declared checks before
   asking a reviewer to reason about what tools can already establish.
5. **Review independently:** inspect the diff plus risk-relevant callers and
   contracts; challenge candidate findings with a concrete failure scenario.
   The coordinator, not a read-only reviewer, runs commands or dispatches workers.
6. **Consolidate:** deduplicate symptoms of one cause, rank by impact and
   confidence, distinguish defects from preference and report uncertainty.
7. **Repair and recheck:** fix actionable findings, validate that the fix
   resolves the scenario and rerun affected checks. New commits invalidate
   old review evidence where relevant.
8. **Stop:** acceptance met, no actionable in-scope defect remains, and final
   gates ran after the last edit; otherwise report an explicit blocker.
9. **Human handoff:** present exact evidence and residual risks. Publication,
   hosted settings, credentials and production operations retain approval.
10. **Learn selectively:** preserve reproducible failures as tests; record
    durable decisions, not full conversations or an ever-growing rules file.

Passing checks do not prove an untested behavioral claim. Conversely, an
unsupported reviewer suggestion does not override a measured contract. When
they disagree, reproduce the scenario and determine whether the test, code or
requirement is wrong; do not resolve the disagreement by voting.

## 6. Claude and Copilot adoption matrix

| Surface | Claude Code | GitHub Copilot family | Repository policy |
| --- | --- | --- | --- |
| Entry instructions | `CLAUDE.md`, imports and scoped rules | Repository/path instructions and host-supported `AGENTS.md` | One portable owner, thin native adapters |
| Skills | Host discovery plus native invocation extensions | Discovery and support depend on IDE/CLI/cloud harness | Portable subset; no assumed parity from equal names |
| Custom roles | Native tool names and main-agent delegation constraints | Tool categories, invocation flags and host-specific agent behavior | Render native metadata; test both actual rosters |
| Hooks | Native event/payload/exit semantics | Local, CLI and cloud semantics differ | One registration per harness; advisory entry never provisions |
| Tool approval | Scoped permissions and managed constraints | Workspace/CLI/cloud approval and trust controls differ | Instructions and hooks are not sandboxes |
| MCP | Project/user discovery, trust and authentication | Native configuration/tool selection per host | Opt-in approval; no smoke-test server startup |
| Review service | Hosted Code Review is distinct from a local reviewer role | Hosted Copilot review is distinct from coding/cloud agent | Advisory AI findings plus deterministic checks and accountable human review |
| Context visibility | Inspect the actual selected context | Inspect customizations and tools in the actual harness | Source selection cannot suppress parent/user/plugin additions |
| Remote execution | Account/service permissions and isolation matter | Cloud agent environment/network/secrets policy matters | No remote enablement as an incidental local cleanup |

Do not install both hosted reviewers to satisfy a checklist. Choose a service
only after measuring useful findings, false positives, latency, cost and data
handling on representative changes.

## 7. Operational acceptance still required

These are relevant operator checks, not permission to change hosted resources:

- Confirm actual branch rules, bypass actors, code-owner eligibility, required
  status names, stale approval handling and conversation resolution.
- Verify tag creation, update and deletion with the intended human and machine
  identities separately; confirm protected release-environment approval.
- Exercise native skill/role discovery, read-only denied operations, bounded
  implementation, hook single execution and missing-bootstrap behavior in each
  intended host/version.
- Confirm effective MCP tool filtering, declined authentication and removal;
  configuration headers are not authorization evidence.
- Run the README/bootstrap path on a clean supported environment and exercise
  an independently installed release outside the checkout.
- Verify private vulnerability reporting and contact ownership, dependency
  graph/audit availability, hosted review configuration and release provenance.
- Treat host Docker-engine access as privileged; a dev container with that access
  is not an isolation boundary for untrusted agent code.
- Recheck published artifacts and installation on the supported OS/Python
  matrix. Local Windows evidence alone cannot certify Linux or hosted CI.

## 8. Deliberately not added

No new orchestration framework, mandatory review swarm, duplicate skill/role,
always-on handbook, model pin, hosted app, MCP server, dependency, generic
configuration layer, speculative backend refactor or user-global setup.
No APM upgrade merely because newer documentation exists. Existing release
cooldown and pinned-runtime compatibility remain in force.

No numerical "production ready" score. The relevant questions are which
behaviors have evidence, which risks remain, and who owns the next action.

## 9. Requested article: how Anthropic approaches code review

The supplied [article](https://claude.dev/blog/solving-code-review-at-anthropic/)
was accessible on 2026-10-28. Its live title was *How the Claude Code team does
code review*, published 2026-10-15. Research read the publisher's Markdown
representation, not a third-party
summary. The analysis below is original synthesis, not a copy of the article.

### Purpose: review throughput without transferring risk to users

The problem is not simply generating more review comments. Code production
can grow faster than human reviewers can check it. The useful outcome is less
human time on routine defects without increasing escaped defects, reverts or
unsafe approvals.

Anthropic reports more than doubled merged PRs alongside a more than 40%
reduction in revert share over its measured period. It also reports mean
review rounds falling from 2.08 to 1.32 and the share needing five or more
rounds falling from 8.9% to 1.5%. These are vendor case-study results, not
independently audited benchmarks or promises for Agent Kit.

### Mechanism: move evidence earlier and verify findings separately

The described process combines pre-PR verification, fresh-context assessment,
AI review, candidate verification/ranking and human risk-based decisions.
The portable lesson is separation of duties:

- The implementer demonstrates the intended outcome.
- A reviewer challenges assumptions and interactions.
- A verification/consolidation step rejects unsupported or duplicate comments.
- A human remains accountable for approval and high-risk changes.

More reviewers are not automatically better. Multiple agents can repeat the
same mistaken assumption. Independent assessment and concrete contrary evidence
matter more than a vote, model branding or a fixed worker count.

Agent Kit already had bounded delegation and read-only review roles. The
missing detail was a consistent candidate-to-finding and patch re-review
procedure. This change puts that detail in the existing feedback-loop owner
and review prompt, without another orchestrator or reviewer roster.
The existing rubric now records evidence-backed statuses instead of a
subjective aggregate threshold; deterministic test and coverage thresholds
remain unchanged.
The follow-up cleanup also removes repeated unchanged-context loading, makes
conventions project-specific and replaces "delete if tests still pass" with
caller/contract checks. Current official sources replace the older best-practices
link; the owning skill and checklist follow the same procedure.
Its resource guard now validates real ISO review dates and rejects missing,
invalid or future dates instead of requiring every reference to claim the same
historical review day.

### Convergence: optimize for resolving defects, not generating rounds

Repeatedly rediscovering the same comment creates work without new evidence.
Useful convergence needs:

1. A fixed target and clear acceptance criteria.
2. Distinct defect classes rather than one comment per repeated line.
3. Explicit resolved, open, withdrawn or accepted dispositions.
4. Re-review of the actual revised patch and newly affected interactions.
5. A bounded loop and escalation when the approach itself is not converging.

The repository already used a bounded feedback loop. It did not need an
additional autonomous retry engine. The revised guidance clarifies that a
passing deterministic check cannot dismiss a concrete, untested failure.

### Reviewer instructions: local failure modes, not a second handbook

The article recommends concise project and review-specific guidance, including
`REVIEW.md` for supported hosted review. The useful content is what constitutes
an important defect here, which assumptions are misleading, required evidence,
and which nits existing tools already own.

For this toolkit the distinctive review risks are incomplete source capture,
ownership/provenance, selection collisions, installed relocation, permission
expansion and accidental side effects. Generic style essays add less value
than regressions for those risks.

Do not add a root review configuration merely to tick a box: choose the actual
review host first, confirm its discovery behavior and link the existing owner.
The existing local review entry point is improved now; hosted-service adoption
remains an operator choice.

### Approval and rollout: principles, not copied infrastructure

The article's human review, CODEOWNERS, protected branches, staged rollout,
merge queues, feature flags and rollback practices serve different failure
modes. They are not a mandatory list of products.

For a pre-release capability/CLI library, relevant rollout is a pinned
candidate, synthetic consumer, real APM delivery, immutable artifacts,
explicit operator publication and a consumer pin/revert path. An application
feature-flag platform or mandatory merge queue would not repair the defects
found here and is not added.

The article's AI review product posts findings rather than granting human
approval. Do not copy an internal low-risk auto-merge policy into this
repository or treat a bot's lack of objections as authorization.

## 10. Requested documentation: Claude Code best practices

The [current page](https://code.claude.com/docs/en/best-practices) was accessible
on 2026-10-28; research read its complete Markdown representation. It is
version-sensitive operational advice, not a timeless specification.

### Instructions versus enforcement

Prompts, project memory and skills guide a probabilistic model. Command checks,
recognized permission rules and the harness can enforce specific conditions.
Repeating a rule in capitals does not turn it into a boundary.

The practical mapping for this repository is:

| Requirement | Appropriate owner | Why |
| --- | --- | --- |
| Explain source ownership and approval expectations | Short policy and scoped instructions | Human/model context |
| Reject malformed manifests, paths and collisions | Application/parser checks | Deterministic accepted-input contract |
| Refuse unsafe generated-output ownership | Renderer and provenance gates | Mutating boundary, not a prose convention |
| Audit dependencies before using them | Bootstrap and CI dependency graph | Ordering must be enforced, not merely requested |
| Restrict a reviewer's available tools | Native role metadata and host permissions | A body saying read-only is not enough |
| Prevent unauthorized hosted merge/publication | Server-side identity/rules/environment controls | Local command patterns can be bypassed |
| Decide whether a finding is a real defect | Evidence-driven review and human judgment | Not reducible to parser success |

Do not overstate this distinction: a deterministic hook still has limited
coverage, trust and timeout/failure semantics. A prompt/agent hook asks another
model to judge; it is not equivalent to a deterministic command checker.
Hooks running with user privileges are not OS isolation.

### Verification as an executable outcome

Give the agent a meaningful pass/fail condition. That means the actual
contract, not a proxy such as well-formed YAML, a successful process launch
or a model-generated confidence score.

The review-package defect illustrates the difference: command success with no
acceptance criteria was being labeled ready. The YAML and template-import
defects likewise show why parsing or a globally present symbol cannot prove a
consumer template works as written.

The documentation describes completion hooks, including host/version-dependent
escape and failure behavior. This review does not install a full verification
command as a repeated stop hook: it is expensive, mutable contributor settings
are not a universal control, and CI already owns the merge-time gate. The
advisory session hook remains small, non-installing and explicitly non-security.

### Context and task shape

Keep project instructions short, specific and useful. Put facts in the project
file, scoped invariants in native rules and procedures in on-demand skills.
Inspect the repository instead of pasting its entire architecture into every
request.

The current page also retires older blanket advice about aggressive context
management, magic emphasis and delegation for automatically better answers.
Its large-context/model defaults are version-dependent. Agent Kit's stricter
portable budgets remain a deliberate compatibility and discoverability policy,
not a claim that every current model needs tiny contexts.

Delegate for meaningful parallelism, separate context or independent assessment,
not as a ritual. A narrow continuous trace is often better done directly.
No new memory service, model pin, context-compaction daemon or worker fleet is
needed for this repository.

### Trust, permissions and sandboxing

Review the effective settings layers and exact native host. A local permission
pattern matches recognized tool calls; it is not proof that arbitrary scripts,
another process, a network client or inherited user tools cannot access data.
Managed controls and actual OS isolation have different purposes.

Do not apply Linux/macOS/WSL sandbox claims to native Windows. Do not call a
development container a sandbox when it can control the host Docker engine.
Do not infer that a command-hook configuration is trusted or executed on every
contributor's machine.

## 11. Current official documentation: implications for both providers

The research consulted current first-party documentation beyond the articles.
Feature availability, preview status and account controls must be rechecked
when the chosen host changes; newer documentation does not upgrade the
repository's pinned APM runtime.

| Primary source | Relevant conclusion | Applied or deliberately deferred |
| --- | --- | --- |
| [Claude review](https://code.claude.com/docs/en/code-review), [customization](https://code.claude.com/docs/en/code-review-customize) | Hosted review and local review are different surfaces; review-only instructions have their own discovery/source rules | Existing local review improved; hosted activation and any root review file deferred until an actual host is selected |
| [Claude memory](https://code.claude.com/docs/en/memory), [skills](https://code.claude.com/docs/en/skills) | General context, scoped rules and on-demand procedures have different loading behavior | Retain canonical ownership, thin adapters and progressive disclosure |
| [Claude subagents](https://code.claude.com/docs/en/sub-agents) | Separate context and native tool limits are useful; delegation is not guaranteed higher quality | Preserve bounded workers and no nested delegation |
| [Claude hooks](https://code.claude.com/docs/en/hooks), [permissions](https://code.claude.com/docs/en/permissions), [sandboxing](https://code.claude.com/docs/en/sandboxing) | Event/payload/failure behavior and true isolation differ from prompts | No-sync session hook; native testing still required; no new stop/guard hook activated |
| [Copilot instruction concepts](https://docs.github.com/en/copilot/concepts/prompting-and-context/custom-instructions), [support matrix](https://docs.github.com/en/copilot/reference/custom-instructions-support) | GitHub.com, IDE review, CLI, chat and cloud agent do not consume identical instruction sets | Document per-surface limits rather than promise universal `AGENTS.md`/`REVIEW.md` discovery |
| [Copilot hooks](https://docs.github.com/en/copilot/reference/hooks-reference), [VS Code hooks](https://code.visualstudio.com/docs/agent-customization/hooks) | CLI/cloud/Local schemas, supported events and approval behavior differ | Preserve native metadata; certify each intended harness separately |
| [Copilot responsible review](https://docs.github.com/en/copilot/responsible-use/code-review) | AI review can miss defects and needs validation and human accountability | No auto-approval policy or bot exemption added |
| [Agent Skills](https://agentskills.io/specification), [VS Code skills](https://code.visualstudio.com/docs/agent-customization/agent-skills) | Portable structure does not standardize every runtime extension | Existing metadata/resource subset and actual APM byte checks retained |
| [GitHub Actions security](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions) | Pins, identities and workflow ordering require explicit controls | Audit-before-install graph and existing narrow grants, not another CI product |
| [GitHub rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets) | Bypass and reference conditions define real protection scope | Strengthen local mutation checks and correct misleading hosted-policy claims |
| [Google engineering review](https://google.github.io/eng-practices/review/reviewer/looking-for.html) | Review correctness, complexity, contracts, tests and understandable design rather than preference | Concrete scenarios, contrary evidence, deduplication and minimal fix directions |

### Important support asymmetries

- At review time, the official Copilot matrix documented broader instruction
  support for GitHub.com code review than IDE code review. A file used by cloud
  review must not be assumed effective in VS Code/Visual Studio review.
- Claude's hosted review-specific instruction behavior is not the same as the
  local review command. Record the service/command as well as the product name.
- Current Copilot documentation describes Actions-dependent agentic review
  capabilities and a narrower fallback when unavailable. Confirm actual review
  execution before assuming repository-wide context was gathered.
- Preview review depths, auto-approval options and agent modes are not a
  portable baseline. None is enabled or required by this change.
- Worker assignments must carry their own governing context. Do not assume a
  delegated agent inherits the coordinator's entire conversation or every
  repository instruction in every harness.

Some guessed documentation paths returned 404 during discovery; research used
the current linked official pages instead. The two requested primary sources
were available. No inaccessible content was reconstructed or represented as read.

## 12. Verification and execution notes

The coordinator independently reran the integrated changes:

| Executed check | Result and limit |
| --- | --- |
| Combined source, provenance, composition, native, template, runtime-resource and prompt tests | 711 passed with four workers |
| Combined release, governance, dependency/pin and composition/provenance tests | 207 passed with four workers |
| Follow-up feedback-loop, review-date, runtime-resource and prompt contracts | 326 passed; scoped format, lint and types passed |
| `task verify -- source` | Passed; source catalog valid |
| `task verify -- docs` | Passed; entries and local links, not remote research accuracy |
| `task verify -- drift` | No deployed drift; all 31 APM policy checks passed |
| `task verify -- roles` | Selected native roster and ownership hashes passed; no regeneration needed |
| `task verify -- dependencies` | Locked Python and Bun audits reported no known vulnerabilities at execution time |
| `uv build --offline --out-dir <session-distributions>` | Fresh sdist and wheel built using the declared isolated backend |
| Fresh local wheel installed with `uv pip install --offline --no-deps --target <session-site> <wheel>` | Only the first-party artifact installed; no dependency or global environment change |
| External synthetic consumer with `python -I <session-check>` | Help, source check, composition and provenance passed; all imported first-party bytes matched the fresh wheel |

The wheel exercise removed checkout root/source import paths while reusing the
existing locked third-party dependencies. It is installed-package evidence, not
a clean-machine dependency/bootstrap certification. An initial build attempt
with `--no-build-isolation` failed because the active environment lacked the
build backend; the normal isolated offline build succeeded without a manifest
change.

The strengthened validators accepted both fresh distributions without changing
their bytes. Existing ignored release ZIPs were not overwritten; a source archive
built before these edits does not match the new canonical source and must be
rebuilt through the documented release workflow before publication.

Final acceptance requires `task verify` and `task apm:smoke` after the last source
edit. Their exact results belong in the completion handoff; focused passes above
must not be substituted for them. Live hosted CI, native permissions,
authentication and server-side protections remain unverified here.

During this review a research worker incorrectly cleaned scratch files with
repository-root extension wildcards, deleting twelve initially unmodified
tracked context documents. Work and tests were paused, the responsible command
was identified, and only those known baseline files were recovered exactly from
`HEAD`. Byte equality was checked before workers resumed; no commit or remote
operation occurred. The initial full gate was interrupted and is not reported
as a pass. This incident is direct evidence that a worker's written scope is
not filesystem isolation; scratch work belongs in an explicit disposable
location, and cleanup must name owned artifacts rather than extensions.

## 13. Provider-neutral rubric follow-up

The follow-up request specifically identified the self-review rubric and required
compatibility across supported providers. The worktree still contained the
earlier audit repairs at the same baseline revision, so this pass reused the
same-day primary research and existing walkthrough rather than repeating the
entire audit or installing another capability.

### Findings and scoped plan

| Finding or question | Action | Acceptance |
| --- | --- | --- |
| Feedback prompt still requested scoring after the rubric changed to evidence statuses | Align the existing prompt, skill, rubric, checklist and iteration log | No request to score the change; the same declared outcomes at every entry point |
| A stopped loop could mean either success or exhausted work | Distinguish COMPLETE, ITERATE and BLOCKED | Unmet required work cannot be reported complete because a budget expired |
| Missing access could be mistaken for an applicability exclusion | Restrict not-applicable to the agreed scope | Unavailable required evidence names a blocker, next action and owner |
| Static checks could be used as evidence for another host | Record provider, host/harness, version and actual surface exercised | Native claims remain distinct from inspection and file/CLI tests |
| Native provider support might require another implementation change | Independent bounded contract assessment | Change native adapters only for a demonstrated defect |

Six focused contract cases failed before the repair. The integrated follow-up
run then passed **363 tests**, including the shared feedback/prompt/runtime
resources and native-delivery tests. Scoped formatting, lint and types passed.
These content-contract tests detect inconsistent declared guidance; they do not
certify a model's compliance.

### Provider assessment

The independent reviewer traced supported-runtime selection, shared-body
rendering, provider-specific metadata, worker closure, provenance and native
ownership. No additional native defect was demonstrated. Existing negative
coverage includes single-provider selection, unsupported runtimes, malformed
definitions, unowned collisions, extra roles, hook state and invocation flags.

The declared adapters remain **Copilot and Claude**. The common rubric is
model/vendor neutral and does not embed provider commands, model names,
permissions or assumptions that one host's result certifies another. Native
metadata remains provider-specific. This does not add support for an unlisted
runtime or guarantee that every account offers a given model or feature.

No new agent, skill, framework, dependency, service, permission, context budget
or runtime adapter was needed. COMPLETE is acceptance of the agreed task scope,
not human approval to merge, publish or deploy.

### What the maintainer still owns

1. Review and publish the source changes through the normal PR and actual
   Windows/Linux CI workflow.
2. Verify/apply hosted branch, bypass, tag-creation and release-environment
   controls; local definitions alone are not enforcement evidence.
3. Use genuinely read-only research toolsets and an appropriate isolation
   boundary for autonomous writers, not written path ownership alone.
4. Exercise each intended native host/version, clean bootstrap and representative
   consumer adoption; record unsupported behavior explicitly.
5. After the reviewed changes are available, deliberately refresh the consumed
   APM dependencies and inspect delivery/provenance. Editing source does not
   automatically update project/user installations; never patch generated copies.

Final repository and real APM acceptance must run after this follow-up's last
edit; their exact results are reported in its completion handoff.
