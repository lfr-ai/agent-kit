# Research and provenance

APM/source baseline reviewed 2026-10-08; repository governance reviewed 2026-10-09;
live GitHub settings rechecked 2026-10-21; agentic capability research refreshed
2026-10-24.
Source content was written for this toolkit; no company
application files, proprietary prompts, or third-party skill bodies were copied.

## Resource-depth refresh, 2026-10-19

Primary pages were fetched again for this refresh, following vendor redirects.
The task expanded linked references, usable assets and concrete quality gates,
not always-on policy or the profile description budgets.

| Verified source | Applied requirement |
| --- | --- |
| [Agent Skills specification](https://agentskills.io/specification) | Metadata, activated procedure and on-demand resources are separate context levels; this toolkit keeps stricter local budgets |
| [VS Code skills](https://code.visualstudio.com/docs/agent-customization/agent-skills) | Repository and personal discovery layers coexist; selected source does not isolate a session |
| [VS Code agents](https://code.visualstudio.com/docs/agent-customization/custom-agents) | Review effective tool access and retain read-only roles for sensitive analysis |
| [VS Code MCP](https://code.visualstudio.com/docs/agent-customization/mcp-servers) | Local servers can execute arbitrary code; review publisher/configuration, trust, authentication and tool exposure |
| [Claude skills](https://code.claude.com/docs/en/skills) | Host-specific invocation/tool extensions are not portable authorization guarantees |
| [Claude subagents](https://code.claude.com/docs/en/sub-agents) | Native tools/model metadata needs its own projection and live test |
| [Claude settings](https://code.claude.com/docs/en/settings) | Permissions have multiple scopes and managed-policy constraints |
| [Claude hooks](https://code.claude.com/docs/en/hooks) | Command hooks execute with user permissions; callbacks are not a universal sandbox |
| [OpenSSF OSPS baseline](https://baseline.openssf.org/versions/2026-08-28-checklist.md) | Source/community controls and hosted access/review/release controls need separate evidence |

The installed CLI remains pinned to APM 0.33.0. Its source tag is the contract
for current runtime behavior. Microsoft's documentation has since moved to
`microsoft.github.io/apm` and now describes newer working-draft contracts as
well as released behavior. These pages are useful for upgrade review, not proof
that the pinned CLI accepts newer fields or semantics. At this review date, the
latest release was 0.35.0 (2026-10-22); the repository's 14-day release cooldown
means reassessing it no earlier than 2026-11-05. The toolkit still selects only
Copilot and Claude.

The pinned [compilation configuration](https://github.com/microsoft/apm/blob/v0.33.0/src/apm_cli/compilation/agents_compiler.py)
and [lifecycle lock](https://github.com/microsoft/apm/blob/v0.33.0/src/apm_cli/install/locking.py)
were also inspected locally. A disposable experiment retained all 53 fullstack
skills in both native locations with skill-tree compilation exclusions; compiler
generation fell from repeated path-resolution scans to about 11 seconds in that
fixture. This is diagnostic evidence, not a cross-platform performance guarantee.
Smoke uses temporary home/lock/cache paths and checks original resource bytes.

Official endpoint/command shapes for all 11 integrations were checked against
their upstream documentation, linked in the
[integration procedure](../packages/shared/.apm/skills/kit-editor/references/mcp.md).
Local package versions and image digests remain deliberate `REVIEWED_*`
placeholders until consumer approval. No MCP was started or authenticated.
Registry resolution is not security vetting; upstream licensing, actual tool
behavior and data disclosure need separate review.

The 2026-10-23 inventory contains 79 canonical skills, 51 instructions,
27 native roles, 40 prompt files, 11 integration names, five asset categories,
and three hooks. These totals are source-tree counts, not claims that every
capability is active in every profile. The machine-readable mapping records
reauthored/consolidated procedures and explicit consumer-owned exclusions.
Native-agent documentation was consulted again: Claude does not consume the
Copilot picker flags, and its Agent(...) main-agent allowlists are not a universal
subagent enforcement mechanism.

## Behavior and standards refresh, 2026-10-24

Public primary documentation was fetched independently of the private local
comparison. No application code, company facts or third-party capability bodies
were copied into portable packages. The comparison confirmed substantial existing
coverage; it identified executable contract gaps rather than a need to install
every named framework.

| Source checked | Applied constraint |
| --- | --- |
| [Agent Skills](https://agentskills.io/specification.md), [VS Code skills](https://code.visualstudio.com/docs/agent-customization/agent-skills), [Claude skills](https://code.claude.com/docs/en/skills) | Keep the portable metadata subset distinct from host extensions; load detailed resources on demand, with existing stricter local budgets |
| [VS Code agents](https://code.visualstudio.com/docs/agent-customization/custom-agents), [Claude subagents](https://code.claude.com/docs/en/sub-agents), [Claude permissions](https://code.claude.com/docs/en/permissions) | Native tool access and permission behavior need host evidence; bounded workers do not imply sandboxing |
| [Context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Retrieve relevant evidence just in time; bounded delegation, durable decisions and compact handoffs instead of repeated whole-context loading |
| [Langfuse prompt versions](https://langfuse.com/docs/prompt-management/features/prompt-version-control), [datasets](https://langfuse.com/docs/evaluation/experiments/datasets) | Exact prompt versions differ from rollout labels; a missing requested label fails; hosted dataset versions are item-state timestamps, not local content fingerprints |
| [Hydra](https://github.com/hydra-ecosystem/hydra), [multirun](https://hydra.cc/docs/tutorials/basic/running_your_app/multi-run/), [instantiation](https://hydra.cc/docs/advanced/instantiate_objects/overview/) | Scope Hydra to parameter/evaluation configuration; bound total calls and cost, freeze lazily composed inputs, and reject untrusted target-driven execution |
| [DSPy Predict](https://dspy.ai/current/api/modules/Predict/), [MIPROv2](https://dspy.ai/current/api/optimizers/MIPROv2/), [saving](https://dspy.ai/current/tutorials/saving/) | Reuse the harness through an input-only candidate; separate optimization/validation/holdout as toolkit policy, record artifact identity, and reject untrusted executable serialization |
| [Trivy image scanning](https://raw.githubusercontent.com/aquasecurity/trivy/main/docs/guide/target/container_image.md), [filtering](https://raw.githubusercontent.com/aquasecurity/trivy/main/docs/guide/configuration/filtering.md), [databases](https://raw.githubusercontent.com/aquasecurity/trivy/main/docs/guide/configuration/db.md) | Scan the actual immutable built image with reviewed scanner bytes, explicit finding policy and failure propagation; retain scanner/database evidence without implying a live scan |
| [PEP 8](https://peps.python.org/pep-0008/), [PEP 257](https://peps.python.org/pep-0257/) | Consistency and public API documentation are conventions; project-specific Ruff, type and docstring checks implement the selected policy rather than every possible preference |
| [OpenSSF OSPS 2026-08-28](https://baseline.openssf.org/versions/2026-08-28-checklist.md), [SLSA 1.2](https://slsa.dev/spec/v1.2/) | Source/build provenance and hosted governance need separate evidence; local templates do not establish a maturity or SLSA level |

Trivy's rendered documentation returned HTTP 403; research used its official
repository's documentation and implementation instead. DSPy's older `learn/`
pages redirect to the `current/` tree, so new references use the latter.
Hydra documentation still identifies the 1.4 line as a release candidate;
this refresh does not certify a stable PyPI release or consumer compatibility.
The typing specification index was reachable but not deeply reviewed; no new
typing-language mandate is attributed to that check.

The locked dependency audit found advisories in `filelock` 4.0.12 and
`setuptools` 84.0.0. Only those transitive packages were resolved to the reported
fixed versions, 4.2.1 and 84.1.0, then audited without syncing before installation.
Security fixes are not delayed by the version-update cooldown. The re-audit
reported no known Python or Bun vulnerabilities; this is advisory evidence at
the review time, not a guarantee against unknown vulnerabilities.

## Cleanup revalidation, 2026-10-26

The [uv locking and syncing contract](https://docs.astral.sh/uv/concepts/projects/sync/)
and [CLI reference](https://docs.astral.sh/uv/reference/cli/) were checked again.
`--locked` prevents lock updates, not environment synchronization. The Task and
CI verification entry points now use `--no-sync`, with a separate first
`uv lock --check` gate so read-only checks retain lock-freshness validation.
Bootstrap remains the explicit provisioning workflow.

Adapter review also used Python's
[finite-number predicate](https://docs.python.org/3.13/library/math.html#math.isfinite),
[installation paths](https://docs.python.org/3.13/library/sysconfig.html) and
[Windows reserved-path semantics](https://docs.python.org/3.13/library/pathlib.html#pathlib.PurePath.is_reserved).
These are runtime contracts, not a reason to change the supported interpreter
range or add another dependency.

The [official APM latest-release metadata](https://api.github.com/repos/microsoft/apm/releases/latest)
and [PyPI metadata](https://pypi.org/pypi/apm-cli/json) both identify 0.35.0.
Its 2026-10-22 publication is still inside the documented cooldown; retaining
0.33.0 is intentional, not a claim that it is the newest release.

The full link check identified documentation migrations and dead endpoints.
Starlette and Uvicorn's upstream READMEs now name
[starlette.dev](https://starlette.dev/) and [uvicorn.dev](https://uvicorn.dev/).
Postman's [schema index](https://schema.postman.com/) supplies the exact v2.1
specification URL; CSpell's sitemap supplies its case-sensitive configuration
path without a trailing slash. The maintained OWASP JWT reference is now
language-neutral. Replacements were fetched directly rather than excluding
failed hosts or accepting additional error statuses.

The [pinned secret scanner's false-positive procedure](https://github.com/Yelp/detect-secrets/tree/v1.5.0#inline-allowlisting)
was used to resolve nine inspected synthetic findings through fixture
annotations and descriptive prose, following the repository's existing
convention. The annotations travel with portable assets;
the baseline and detector/filter settings remain unchanged. Unrelated source
lines are not exempted.

## Improvement prompt grounding, 2026-10-26

The library now has 41 prompt facades. The added improvement entry point reuses
the existing audit, simplification, refactoring, consistency and modernization
owners; it does not add a skill, role, integration or larger context budget.

- [VS Code prompt files](https://code.visualstudio.com/docs/agent-customization/prompt-files):
  reusable, manually invoked task entry points; the documented Local-harness
  scope is not a guarantee for an SDK or other host.
- [Google engineering review guidance](https://google.github.io/eng-practices/review/reviewer/looking-for.html):
  review complexity, over-engineering, naming, tests and understandability;
  code golf is not maintainability.
- [PEP 8](https://peps.python.org/pep-0008/): project consistency takes precedence,
  and style cleanup does not justify breaking compatibility.
- [Context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents):
  retrieve relevant evidence progressively rather than loading the entire
  repository, catalog or raw tool history into every task.

These pages were fetched for this change. Prompt/source checks verify structure,
selection and delivery; they do not prove an agent obeyed every convention.

## Structure and callable grounding, 2026-10-26

The existing improvement/alignment prompts now include semantic centralization,
file/module naming, package boundaries, partial application and decorator
contracts. Detail remains in the owning consistency and Python references;
no new skill, prompt, role, permission or context budget was introduced.

- [PEP 8 naming](https://peps.python.org/pep-0008/#package-and-module-names):
  short lowercase module/package names and project consistency, not a
  universal one-class-per-file rule.
- [PyPA layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/):
  distribution/import isolation is separate from feature-folder depth.
- [Python 3.13 functools](https://docs.python.org/3.13/library/functools.html):
  partial keyword overrides, reference retention, descriptor binding, wrapper
  metadata and cache semantics were checked against the supported baseline.
- [Python 3.14 Placeholder](https://docs.python.org/3.14/library/functools.html#functools.Placeholder):
  the newer feature is not valid for the toolkit's minimum Python 3.13.
- [Signature inspection](https://docs.python.org/3.13/library/inspect.html#inspect.signature):
  default unwrapping supports inspection, not behavioral or permission proof.
- [Engineering review](https://google.github.io/eng-practices/review/reviewer/looking-for.html):
  assess actual cohesion, naming, reuse and understandable complexity rather
  than treating extraction or centralization as an end in itself.
- [CommonMark fenced code](https://spec.commonmark.org/0.31.2/#fenced-code-blocks):
  literal examples are not Markdown links. A modern generic-function example
  exposed a false positive; source, documentation and resource checks now share
  the bounded inline-link extractor and ignore matching backtick/tilde fences.
  Negative regressions retain real unsafe-link rejection and prevent code-only
  example links from satisfying resource discoverability.

## Primary sources

- [APM release 0.33.0](https://github.com/microsoft/apm/releases/tag/v0.33.0)
- [APM quickstart](https://microsoft.github.io/apm/quickstart/)
- [APM releases](https://github.com/microsoft/apm/releases)
- [Current APM documentation](https://microsoft.github.io/apm/)
- [APM policy reference](https://microsoft.github.io/apm/enterprise/policy-reference/)
- [APM lockfile reference](https://microsoft.github.io/apm/reference/lockfile-spec/)
- [APM CLI audit](https://microsoft.github.io/apm/reference/cli/audit/)
- [Pinned APM 0.33.0 policy discovery source](https://github.com/microsoft/apm/blob/v0.33.0/src/apm_cli/policy/discovery.py)
- [Agent Skills specification](https://agentskills.io/specification)
- [VS Code progressive skill discovery](https://code.visualstudio.com/docs/agent-customization/agent-skills)
- [VS Code MCP tool selection](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [Claude skill context and invocation controls](https://code.claude.com/docs/en/skills)
- [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Langfuse prompt management](https://langfuse.com/docs/prompt-management/get-started)
- [Langfuse prompt versioning and labels](https://langfuse.com/docs/prompt-management/features/prompt-version-control)
- [Langfuse evaluation experiments](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk)
- [Hydra releases and compatibility](https://github.com/hydra-ecosystem/hydra)
- [Hydra object instantiation and execution boundaries](https://hydra.cc/docs/advanced/instantiate_objects/overview/)
- [Python style guide](https://peps.python.org/pep-0008/)
- [Python docstring conventions](https://peps.python.org/pep-0257/)
- [Ruff preview-rule policy](https://docs.astral.sh/ruff/preview/)
- [VS Code instructions](https://code.visualstudio.com/docs/agent-customization/custom-instructions)
- [VS Code custom agents](https://code.visualstudio.com/docs/agent-customization/custom-agents)
- [Claude subagent tools and invocation](https://code.claude.com/docs/en/sub-agents)
- [Claude memory/discovery](https://code.claude.com/docs/en/memory)
- [Agent Plugins portable subset](https://agent-plugins.org/)

## GitHub governance grounding

- [CODEOWNERS matching and write-access requirements](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
- [Dependency graph and dependency review prerequisites](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-graph)
- [Private vulnerability reporting requires hosted enablement](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/configuring-private-vulnerability-reporting-for-a-repository)
- [Secure Actions use and immutable pins](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions)
- [Codecov YAML configuration](https://docs.codecov.com/docs/codecov-yaml)
- [Codecov commit status configuration](https://docs.codecov.com/docs/commit-status)
- [CodeRabbit YAML configuration](https://docs.coderabbit.ai/guides/configure-coderabbit)
- [CodeRabbit configuration reference](https://docs.coderabbit.ai/reference/configuration)
- [Reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)
- [Artifact attestations and plan availability](https://docs.github.com/en/actions/concepts/security/artifact-attestations)
- [Existing-tag and draft release flags](https://cli.github.com/manual/gh_release_create)
- [Actionlint 1.7.12](https://github.com/rhysd/actionlint/releases/tag/v1.7.12)
- [Repository rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
- [Dependency review action 5.0.0](https://github.com/actions/dependency-review-action/releases/tag/v5.0.0)
- [Dependency review API and pull request workflow](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-review)
- [OpenSSF Scorecard action 2.4.4](https://github.com/ossf/scorecard-action/releases/tag/v2.4.4)
- [Generated release notes](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes)

## Pin resolution

Action, hook, and image pins were resolved from public release and tag metadata,
not guessed from version names. Pre-commit runs `actionlint` and `zizmor` on
workflows; hosted execution is a separate gate.

[The pinned artifact uploader](https://github.com/actions/upload-artifact/blob/v7.0.2/README.md)
preserves hierarchy for multiple paths. Release staging deliberately flattens the
verified inventory before upload rather than assuming a flattened download.

## Python data-library guidance

- [Sphinx reStructuredText inline markup](https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html#inline-markup)
- [Docutils inline literal reference](https://docutils.sourceforge.io/docs/user/rst/quickref.html#inline-markup)
- [CommonMark code spans](https://spec.commonmark.org/0.31.2/#code-spans)
- [Pydantic models](https://pydantic.dev/docs/validation/latest/concepts/models/)
- [Pydantic fields](https://pydantic.dev/docs/validation/latest/concepts/fields/)
- [Pydantic validators](https://pydantic.dev/docs/validation/latest/concepts/validators/)
- [Pydantic serialization](https://pydantic.dev/docs/validation/latest/concepts/serialization/)
- [Pydantic v1-to-v2 migration](https://pydantic.dev/docs/validation/latest/get-started/migration/)
- [Pydantic Settings](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/)
- [Polars 2.0 release](https://pola.rs/posts/release-polars-2/)
- [Polars 2.0 upgrade guide](https://docs.pola.rs/releases/upgrade/2/)
- [Polars lazy API](https://docs.pola.rs/user-guide/lazy/using/)
- [Polars lazy schemas](https://docs.pola.rs/user-guide/lazy/schemas/)
- [Polars Python UDFs](https://docs.pola.rs/user-guide/expressions/user-defined-python-functions/)

Pydantic v2 and Polars 2 procedures are authored in the backend capability bundle;
the toolkit itself does not add either library as a production dependency.
Validation examples are syntax/resource-tested without installing Polars into the
toolkit, while consumers run behavioral tests against their own locked versions.
Polars 2.0.0 was confirmed as the current major at authoring time from its
[official release announcement](https://pola.rs/posts/release-polars-2/) and
[PyPI metadata](https://pypi.org/project/polars/). The toolkit environment
currently resolves Pydantic 2.13.5 transitively; the consumer lockfile remains
authoritative for both libraries.

## Revalidation

Update compatibility evidence when changing APM, native runtimes, metadata, policy,
or installation ownership. Treat released source as authoritative over newer
unreleased documentation. Context7 quota failures were resolved with primary sources.
