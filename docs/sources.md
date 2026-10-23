# Research and provenance

APM/source baseline reviewed 2026-10-08; repository governance reviewed 2026-10-09;
live GitHub settings rechecked 2026-10-21.
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

The tagged APM producer documents were compared with current `main`.
[Skills](https://github.com/microsoft/apm/blob/v0.33.0/docs/src/content/docs/producer/author-primitives/skills.md)
and [MCP](https://github.com/microsoft/apm/blob/v0.33.0/docs/src/content/docs/producer/author-primitives/mcp-as-primitive.md)
matched at review. Current instructions/agents and hooks/commands documentation
had newer behavior absent from the pin; do not infer newer agent fields or
Cursor hook-import semantics from a `main` example.
The toolkit still selects only Copilot and Claude.

The pinned [compilation configuration](https://github.com/microsoft/apm/blob/v0.33.0/src/apm_cli/compilation/agents_compiler.py)
and [lifecycle lock](https://github.com/microsoft/apm/blob/v0.33.0/src/apm_cli/install/locking.py)
were also inspected locally. A disposable experiment retained all 35 fullstack
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

The setup-completeness review (2026-10-09, refreshed 2026-10-10 for the Pydantic v2 and
Polars additions) enumerated 74 canonical skills,
31 instructions, 24 agent roles, 24 prompt facades, 22 skill scripts,
11 integration names, five asset categories, and three hooks.
The machine-readable mapping records
reauthored/consolidated procedures and explicit consumer-owned exclusions.
Native-agent documentation was consulted again: Claude does not consume the
Copilot picker flags, and its Agent(...) main-agent allowlists are not a universal
subagent enforcement mechanism.

## Primary sources

- [APM release 0.33.0](https://github.com/microsoft/apm/releases/tag/v0.33.0)
- [APM quickstart](https://microsoft.github.io/apm/quickstart/)
- [Released manifest schema](https://github.com/microsoft/apm/blob/v0.33.0/docs/src/content/docs/reference/manifest-schema.md)
- [Released policy reference](https://github.com/microsoft/apm/blob/v0.33.0/docs/src/content/docs/enterprise/policy-reference.md)
- [Released policy discovery](https://github.com/microsoft/apm/blob/v0.33.0/src/apm_cli/policy/discovery.py)
- [Released drift detection](https://github.com/microsoft/apm/blob/v0.33.0/docs/src/content/docs/enterprise/drift-detection.md)
- [Agent Skills specification](https://agentskills.io/specification)
- [VS Code progressive skill discovery](https://code.visualstudio.com/docs/agent-customization/agent-skills)
- [VS Code MCP tool selection](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [Claude skill context and invocation controls](https://code.claude.com/docs/en/skills)
- [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [VS Code instructions](https://code.visualstudio.com/docs/agent-customization/custom-instructions)
- [VS Code custom agents](https://code.visualstudio.com/docs/copilot/customization/custom-agents)
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
