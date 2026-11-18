# Research and provenance

Toolkit source was written for this repository; no company application files,
proprietary prompts or third-party skill bodies were copied. Each dated section
lists the primary sources checked and the constraint applied. Current web
documentation is upgrade evidence, not proof of behavior in a pinned version.

## Pins

| Item | Pin | Note |
| --- | --- | --- |
| APM CLI | 0.35.0 | Upgraded after the 14-day cooldown on 2026-11-05; [release notes](https://github.com/microsoft/apm/releases/tag/v0.35.0) describe frozen-install integrity and deployment ownership fixes. The dependency audit passed before synchronization. The legacy local-owner ledger limitation remains documented in [compatibility](compatibility.md). |
| Actions, hooks, images | Commit SHA or digest | Resolved from release/tag metadata, not version names; pre-commit runs `actionlint` and `zizmor` |
| `filelock`, `setuptools` | 4.2.1, 84.1.0 | Advisory fixes resolved 2026-10-24 and audited before sync; security fixes skip the cooldown |
| Pydantic, Polars | Consumer lock | Backend capability guidance only; the toolkit resolves Pydantic 2.13.5 transitively and does not install Polars |

The [pinned artifact uploader](https://github.com/actions/upload-artifact/blob/v7.0.2/README.md)
preserves hierarchy for multiple paths, so release staging flattens the verified
inventory before upload.

## Infrastructure and feedback-loop review, 2026-11-16

Current official documentation was consulted for the focused cleanup, without
deploying resources or upgrading the pinned toolchain. Supported platform
features are not evidence that an existing environment is correctly configured.

| Source | Applied constraint |
| --- | --- |
| [Container Apps ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview), [networking](https://learn.microsoft.com/en-us/azure/container-apps/networking), [custom domains](https://learn.microsoft.com/en-us/azure/container-apps/custom-domains-certificates) | Native ingress/TLS needs no default Front Door. Environment accessibility and app ingress differ; keep private DNS and domain ownership explicit. |
| [Azure load-balancing choices](https://learn.microsoft.com/en-us/azure/architecture/guide/technology-choices/load-balancing-overview), [Front Door WAF](https://learn.microsoft.com/en-us/azure/web-application-firewall/afds/afds-overview) | Add an edge or gateway for an actual WAF/global-routing/API-policy requirement; never replace a configured WAF with unprotected ingress silently. |
| [Container Apps secrets](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets), [GitHub Azure OIDC](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure) | Runtime managed identities read Key Vault references; deployment federation and data-plane RBAC remain separately scoped. |
| [Terraform Azure backend](https://developer.hashicorp.com/terraform/language/backend/azurerm), [remote-state bootstrap](https://learn.microsoft.com/en-us/azure/developer/terraform/store-state-in-azure-storage), [Bicep deployment modes](https://learn.microsoft.com/en-us/azure/azure-resource-manager/templates/deployment-modes) | Separate backend bootstrap, Entra/OIDC and native blob locking; incremental Bicep does not delete omitted resources or merge omitted properties. |
| [Container Apps log options](https://learn.microsoft.com/en-us/azure/container-apps/log-options), [retention](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/data-retention-archive), [OpenTelemetry](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable) | Console collection owns logs; optional Insights owns traces. Avoid duplicate instrumentation/exporters. Live streaming is not retained history. |
| [Container Apps metrics](https://learn.microsoft.com/en-us/azure/container-apps/metrics), [metric alerts](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-metric-overview), [action groups](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/action-groups) | Use supported Requests/RestartCount metrics; reference a caller-owned Teams-capable group or create email receivers. Test real delivery separately. |
| [Activity Log](https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/activity-log) | Subscription control-plane export is distinct from Entra, resource-internal and business auditing; source retention and exported-data retention differ. |
| [VS Code customization](https://code.visualstudio.com/docs/copilot/copilot-customization), [scoped instructions](https://code.visualstudio.com/docs/copilot/customization/custom-instructions), [pytest cache](https://docs.pytest.org/en/stable/how-to/cache.html), [pre-commit](https://pre-commit.com/), [Task up-to-date checks](https://taskfile.dev/docs/guide/up-to-date) | Prefer task-relevant context and focused tests; reuse installed tool environments. Do not add caching to correctness gates without proving complete input coverage. |

No preview metric, new orchestration layer or automatic platform detection was
adopted. Native IDE discovery, cloud reachability, notification delivery and
measured developer latency need separate observed evidence.

## Feedback and hygiene review, 2026-11-04

Primary sources were fetched and checked on this date. Official documentation
describes tool contracts; vendor engineering studies supply evidence in their
reported environments, not independent certification of this repository.
No dependency or host version was upgraded by this review.

| Source | Applied constraint |
| --- | --- |
| [Ruff RUF100](https://docs.astral.sh/ruff/rules/unused-noqa/), [PGH003](https://docs.astral.sh/ruff/rules/blanket-type-ignore/), [PGH004](https://docs.astral.sh/ruff/rules/blanket-noqa/) | Keep suppressions narrow and remove stale ones. These rules do not enforce an explanatory reason; the repository gate adds that contract. Preserve other tools' directives when removing a `noqa`. |
| [Ruff PLR2004](https://docs.astral.sh/ruff/rules/magic-value-comparison/) | Name behavioral values by intent and unit. Ruff covers comparisons; the existing AST checker also covers assignments, arguments and production templates. Literal test expectations remain intentional. |
| [pytest strict mode](https://docs.pytest.org/en/stable/reference/reference.html#confval-strict), [strict xfail](https://docs.pytest.org/en/stable/how-to/skipping.html#strict-parameter) | The pinned pytest 9 suite uses `strict = true`, including `strict_xfail`: unexpected xfail passes expose stale markers. Required unavailable checks remain blockers. |
| [GitHub Actions permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions) | Keep explicit least-privilege tokens and human publication boundaries; committed configuration is not evidence that hosted enforcement was exercised. |
| [Demystifying evaluations for agents](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) | Separate task, trial, grader and observed outcome; inspect artifacts, retain regressions and investigate grader disagreements. Vendor guidance is not a measured improvement for this kit. |
| [Infrastructure noise in coding evaluations](https://www.anthropic.com/research/infrastructure-noise) | Harness resource limits can change measured outcomes. Record the environment, budgets and infrastructure failures; do not attribute every score change to the prompt or model. The reported benchmark effects are not universal thresholds. |
| [Skill authoring best practices](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills/best-practices#evaluation-and-iteration) | Build representative evaluations and a baseline before extensive instructions; iterate using observed task outcomes and test the models intended for use. This is vendor guidance, not evidence that this toolkit improves behavior. |

The [repository evaluation cases and run instructions](../tests/evals/README.md)
define synthetic tasks and a results format; the cases are not observations.
For behavior claims, record real runs in the named host and version, compare
baseline and candidate under the same conditions, and report all attempts.
The checker verifies record completeness only: it neither runs a model nor
authenticates observations. No model run, benchmark, paid provider run, native
IDE certification or hosted permission check was performed by consulting these
sources.

## Cleanup refresh, 2026-11-03

- [PEP 257](https://peps.python.org/pep-0257/), [Google Python style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings):
  concise behavioral docstrings; no boilerplate driven by parameter count.
- [Ruff rules](https://docs.astral.sh/ruff/rules/), [preview selection](https://docs.astral.sh/ruff/settings/#lint_explicit-preview-rules):
  all 59 linter families accounted for; DOC preview rules selected explicitly.
- [VS Code custom agents](https://code.visualstudio.com/docs/agent-customization/custom-agents),
  [file reference](https://code.visualstudio.com/docs/agents/reference/custom-agent-file-reference):
  picker visibility and model invocation are independent; extension agents
  cannot be hidden by shared role metadata.
- [uv audit](https://docs.astral.sh/uv/reference/cli/#uv-audit): JSON is a
  preview contract; the wrapper validates schema, counts and exit status.
- [functools.wraps](https://docs.python.org/3/library/functools.html#functools.wraps),
  [ParamSpec](https://docs.python.org/3/library/typing.html#typing.ParamSpec):
  wrapper metadata is not signature checking or async preservation.
- [Logging cookbook](https://docs.python.org/3/howto/logging-cookbook.html#adding-handlers-other-than-nullhandler-to-a-logger-in-a-library):
  configure handlers at the application boundary.

## Modernization refresh, 2026-11-02

Owning references record the contracts and unverified runtime checks:
[Python](../packages/backend/.apm/skills/kit-python-service/SKILL.md) (`TypeIs`
versus `TypeGuard`, typed decorators),
[Temporal](../packages/temporal/.apm/skills/kit-temporal/references/guide.md),
[identity](../packages/identity/.apm/skills/kit-identity/references/guide.md),
[client authentication](../packages/frontend/.apm/skills/kit-client-auth/references/guide.md),
[dependency auditing](dependency-security.md) and the
[runtime guard](../packages/shared/.apm/skills/kit-agent-runtime/references/guards.md).

## Agentic review and enforcement refresh, 2026-10-28

Conclusions are in the [development review](agentic-development-review.md).

- [Claude Code team code review](https://claude.dev/blog/solving-code-review-at-anthropic/):
  separate implementation, finding verification and human approval; vendor
  metrics are not toolkit guarantees.
- [Claude Code best practices](https://code.claude.com/docs/en/best-practices):
  executable outcomes and checkers over stronger wording or forced fan-out.
- [Claude review customization](https://code.claude.com/docs/en/code-review-customize),
  [Copilot instruction support](https://docs.github.com/en/copilot/reference/custom-instructions-support):
  discovery differs per surface; a file does not prove a service is active.
- [Claude hooks](https://code.claude.com/docs/en/hooks), [Copilot hooks](https://docs.github.com/en/copilot/reference/hooks-reference):
  verify event and failure contracts per host; session context must not provision.
- [GitHub rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets):
  whole-ruleset bypass and tag creation differ from approval exceptions and immutability.
- [Google engineering review](https://google.github.io/eng-practices/review/reviewer/looking-for.html):
  correctness, contracts and complexity over style preference.

## Cleanup revalidation, 2026-10-26

- [uv sync](https://docs.astral.sh/uv/concepts/projects/sync/), [uv CLI](https://docs.astral.sh/uv/reference/cli/):
  `--locked` prevents lock updates, not syncing; Task and CI use `--no-sync`
  after a separate `uv lock --check`.
- [math.isfinite](https://docs.python.org/3.13/library/math.html#math.isfinite),
  [sysconfig](https://docs.python.org/3.13/library/sysconfig.html),
  [reserved paths](https://docs.python.org/3.13/library/pathlib.html#pathlib.PurePath.is_reserved):
  adapter runtime contracts.
- Link-check replacements: [starlette.dev](https://starlette.dev/),
  [uvicorn.dev](https://uvicorn.dev/), [Postman schemas](https://schema.postman.com/).
- [detect-secrets inline allowlisting](https://github.com/Yelp/detect-secrets/tree/v1.5.0#inline-allowlisting):
  nine synthetic findings annotated; baseline and filters unchanged.

## Prompt and structure grounding, 2026-10-26

- [VS Code prompt files](https://code.visualstudio.com/docs/agent-customization/prompt-files):
  manually invoked entry points; Local scope is not a guarantee for other hosts.
- [PEP 8](https://peps.python.org/pep-0008/) and its
  [naming section](https://peps.python.org/pep-0008/#package-and-module-names):
  project consistency first; no one-class-per-file rule.
- [PyPA layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/):
  import isolation is separate from folder depth.
- [functools 3.13](https://docs.python.org/3.13/library/functools.html),
  [Placeholder 3.14](https://docs.python.org/3.14/library/functools.html#functools.Placeholder),
  [inspect.signature](https://docs.python.org/3.13/library/inspect.html#inspect.signature):
  `Placeholder` is not available on the 3.13 minimum.
- [CommonMark fenced code](https://spec.commonmark.org/0.31.2/#fenced-code-blocks):
  code-fence examples are not links; the shared link extractor ignores fences.

## Behavior and standards refresh, 2026-10-24

Fetched independently of a private local comparison; nothing was copied.

| Source | Constraint applied |
| --- | --- |
| [Agent Skills](https://agentskills.io/specification.md), [VS Code skills](https://code.visualstudio.com/docs/agent-customization/agent-skills), [Claude skills](https://code.claude.com/docs/en/skills) | Portable metadata subset; resources load on demand |
| [VS Code agents](https://code.visualstudio.com/docs/agent-customization/custom-agents), [Claude subagents](https://code.claude.com/docs/en/sub-agents), [Claude permissions](https://code.claude.com/docs/en/permissions) | Tool access needs host evidence; workers are not sandboxes |
| [Context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Just-in-time retrieval, compact handoffs |
| [Langfuse versions](https://langfuse.com/docs/prompt-management/features/prompt-version-control), [datasets](https://langfuse.com/docs/evaluation/experiments/datasets) | Versions differ from labels; missing labels fail |
| [Hydra](https://github.com/hydra-ecosystem/hydra), [multirun](https://hydra.cc/docs/tutorials/basic/running_your_app/multi-run/), [instantiation](https://hydra.cc/docs/advanced/instantiate_objects/overview/) | Bound calls and cost; reject untrusted targets; 1.4 is a release candidate |
| [DSPy Predict](https://dspy.ai/current/api/modules/Predict/), [MIPROv2](https://dspy.ai/current/api/optimizers/MIPROv2/), [saving](https://dspy.ai/current/tutorials/saving/) | Input-only candidate; reject untrusted executable serialization |
| [Trivy images](https://raw.githubusercontent.com/aquasecurity/trivy/main/docs/guide/target/container_image.md), [filtering](https://raw.githubusercontent.com/aquasecurity/trivy/main/docs/guide/configuration/filtering.md), [databases](https://raw.githubusercontent.com/aquasecurity/trivy/main/docs/guide/configuration/db.md) | Scan the immutable built image; rendered docs returned HTTP 403, so repository docs were used |
| [OpenSSF OSPS 2026-08-28](https://baseline.openssf.org/versions/2026-08-28-checklist.md), [SLSA 1.2](https://slsa.dev/spec/v1.2/) | Local templates establish no maturity or SLSA level |

## Resource-depth refresh, 2026-10-19

| Source | Constraint applied |
| --- | --- |
| [Agent Skills specification](https://agentskills.io/specification) | Metadata, procedure and resources are separate context levels |
| [VS Code skills](https://code.visualstudio.com/docs/agent-customization/agent-skills) | Repository and personal layers coexist; selection does not isolate |
| [VS Code MCP](https://code.visualstudio.com/docs/agent-customization/mcp-servers) | Local servers can execute code; review trust, auth and tools |
| [Claude settings](https://code.claude.com/docs/en/settings), [hooks](https://code.claude.com/docs/en/hooks) | Multiple permission scopes; hooks run with user permissions |

The pinned [compiler](https://github.com/microsoft/apm/blob/v0.33.0/src/apm_cli/compilation/agents_compiler.py)
and [lock](https://github.com/microsoft/apm/blob/v0.33.0/src/apm_cli/install/locking.py)
were inspected: with skill-tree exclusions, a disposable fullstack fixture kept
all 53 skills and compiled in about 11 seconds (diagnostic only). Endpoints for
all 11 integrations are linked from the
[integration procedure](../packages/shared/.apm/skills/kit-editor/references/mcp.md);
`REVIEWED_*` placeholders remain until consumer approval.

Census 2026-10-23: 79 skills, 51 instructions, 27 native roles, 40 prompt files,
11 integration names, five asset categories, three hooks (source-tree counts).

## Primary sources

APM and agent hosts:
[quickstart](https://microsoft.github.io/apm/quickstart/),
[releases](https://github.com/microsoft/apm/releases),
[policy](https://microsoft.github.io/apm/enterprise/policy-reference/),
[lockfile](https://microsoft.github.io/apm/reference/lockfile-spec/),
[manifest](https://microsoft.github.io/apm/reference/manifest-schema/) (virtual
packages use `owner/repo/path#ref`),
[audit](https://microsoft.github.io/apm/reference/cli/audit/),
[0.33.0 policy discovery](https://github.com/microsoft/apm/blob/v0.33.0/src/apm_cli/policy/discovery.py),
[VS Code instructions](https://code.visualstudio.com/docs/agent-customization/custom-instructions),
[Claude memory](https://code.claude.com/docs/en/memory),
[Agent Plugins](https://agent-plugins.org/),
[Copier configuration](https://copier.readthedocs.io/en/stable/configuring/),
[Langfuse experiments](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk),
[Ruff preview policy](https://docs.astral.sh/ruff/preview/).

GitHub governance:
[CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners),
[dependency graph](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-graph),
[dependency review](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-review),
[dependency review action 5.0.0](https://github.com/actions/dependency-review-action/releases/tag/v5.0.0),
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/configuring-private-vulnerability-reporting-for-a-repository),
[Actions hardening](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions),
[reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows),
[artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations),
[gh release create](https://cli.github.com/manual/gh_release_create),
[generated release notes](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes),
[actionlint 1.7.12](https://github.com/rhysd/actionlint/releases/tag/v1.7.12),
[Scorecard action 2.4.4](https://github.com/ossf/scorecard-action/releases/tag/v2.4.4),
[Codecov YAML](https://docs.codecov.com/docs/codecov-yaml),
[Codecov status](https://docs.codecov.com/docs/commit-status),
[CodeRabbit configuration](https://docs.coderabbit.ai/guides/configure-coderabbit),
[CodeRabbit reference](https://docs.coderabbit.ai/reference/configuration).

Python data libraries and markup:
[Pydantic models](https://pydantic.dev/docs/validation/latest/concepts/models/),
[fields](https://pydantic.dev/docs/validation/latest/concepts/fields/),
[validators](https://pydantic.dev/docs/validation/latest/concepts/validators/),
[serialization](https://pydantic.dev/docs/validation/latest/concepts/serialization/),
[v2 migration](https://pydantic.dev/docs/validation/latest/get-started/migration/),
[settings](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/),
[Polars 2.0](https://pola.rs/posts/release-polars-2/),
[upgrade guide](https://docs.pola.rs/releases/upgrade/2/),
[lazy API](https://docs.pola.rs/user-guide/lazy/using/),
[lazy schemas](https://docs.pola.rs/user-guide/lazy/schemas/),
[Python UDFs](https://docs.pola.rs/user-guide/expressions/user-defined-python-functions/),
[Polars on PyPI](https://pypi.org/project/polars/),
[Sphinx inline markup](https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html#inline-markup),
[Docutils literals](https://docutils.sourceforge.io/docs/user/rst/quickref.html#inline-markup),
[CommonMark code spans](https://spec.commonmark.org/0.31.2/#code-spans).

## Revalidation

Update this record when changing APM, native runtimes, metadata, policy or
installation ownership. Released source outranks newer unreleased documentation.
