# Agentic development review

Reviewed 2026-11-04. A source and workflow review, not production, native-host,
model-quality or hosted-permission certification. Article sources are in
[sources](sources.md#agentic-review-and-enforcement-refresh-2026-10-28).

## 1. Architecture

Keep ports-and-adapters and a stdlib-only Core. The import gate forbids
Infrastructure importing Application or Presentation, matching the
[architecture contract](../.agents/knowledge-base/architecture.md).

## 2. Capability ownership

One canonical source, explicit selections, unchanged context budgets and
no-overwrite composition. Never copy installed skills back into source or
refresh ownership hashes to hide drift.

## 3. Docstrings and decorators

Docstrings describe behavior: constraints, effects, failures and return shapes.
Parameter count alone does not justify sections.
[Python guidance](../packages/backend/.apm/skills/kit-python-service/SKILL.md)
owns examples and the checker. Use typed decorators only for demonstrated
cross-cutting duplication, preserving signatures, metadata, exceptions and async
semantics.

## 4. Roles

`kit-orchestrator` and `kit-debug` are the main agents. Implementation,
test-authoring, refactoring and review roles are hidden bounded workers. No
second DevOps coordinator: its implementer and infrastructure reviewer remain.
See [native roles](../packages/shared/.apm/skills/kit-agent-runtime/references/native-roles.md).

## 5. Logging and toolchain

Stdlib logging at the owning boundary: diagnostics to stderr, results to stdout,
no credentials, no duplicate exception logging. Ruff and ty stay. All 59 pinned
Ruff linter families are selected or classified; preview DOC rules are selected
by exact code.

## 6. New projects

The [new-project prompt](../packages/shared/.apm/prompts/kit-new-project.prompt.md)
reuses the bootstrap, conventions, architecture and verification skills. No new
scaffolding engine or principle-specific reviewer roster.

## 7. Development loop

1. Identify the outcome, owning source, callers, rules and nearest proving check.
2. Plan observable acceptance and negative cases. Delegate only independent,
   substantial work with disjoint paths and stop conditions.
3. Reproduce a defect, keep its failing test, fix the cause.
4. Run focused deterministic checks before independent review.
5. Challenge each finding with a concrete failure scenario; separate defects
   from preferences. Do not settle test-versus-reviewer disagreements by vote.
6. Audit owned outputs before refreshing them; run `task verify` and
   `task apm:smoke` after the final edits.
7. Report exact evidence, unavailable checks and next owners. Completion is not
   approval to stage, publish, merge, deploy or change hosted settings.

Owners: [planning](../packages/shared/.apm/skills/kit-change-plan/SKILL.md),
[delegation](../packages/shared/.apm/skills/kit-subagent-delivery/SKILL.md),
[review](../packages/shared/.apm/prompts/kit-review-change.prompt.md),
[feedback](../packages/shared/.apm/skills/kit-feedback-loop/SKILL.md),
[verification](../packages/shared/.apm/skills/kit-verify-change/SKILL.md).
Record durable failures as regressions, not more always-on prose.

### Fast feedback and context ownership

The everyday loop is one behavior, its owning source and a focused test. Use
`task test -- <path> -n 0` for a small scope; use `--lf` while fixing failures.
Full verification belongs at integration/handoff and CI, not after each edit.
The [command matrix](../PROJECT.md#commands) is authoritative; this review does
not introduce another gate registry or mandatory checklist runner.

Keep root instructions short. Path-scoped instructions carry language rules;
skills supply procedures only when selected. The session hook checks whether
the three entry documents exist; it does not read or inject their contents.
The edit hook examines one in-checkout Python file and caps diagnostic output.
Neither hook installs tools, invokes a model, scans the whole catalog, or grants
permission. Native host timeouts bound them; observed IDE latency still needs a
named-host measurement.

Use a worker when a substantial independent slice benefits from separate
context, not for every lookup or test invocation. Give it an explicit write set
and return only changes, evidence and blockers. Reuse reports rather than
re-reading its entire scope. Do not add user-global skills, MCP services or
duplicate instructions to make this repository appear more capable.
Parent, user and plugin customizations can still add context; repository budgets
do not measure or control those independently owned layers.

The [current official-source review](sources.md#infrastructure-and-feedback-loop-review-2026-11-16)
supports selective customization, cached tool environments and focused tests.
It does not establish a model-quality or development-time improvement for
this checkout. Measure comparable tasks before claiming one.

## 8. Repaired contracts

The tests are the evidence, not old test counts.

| Boundary | Required behavior |
| --- | --- |
| [Filesystem capture](../src/agent_kit/infrastructure/catalog.py), [provenance](../src/agent_kit/application/provenance/hashes.py) | Surface read failures; never attest missing or placeholder bytes |
| [Composition](../src/agent_kit/application/catalog/planning.py) | Reject generated-selection collisions before publication |
| [Release products](../scripts/checks/release.py) | Reject unsafe checksum paths, incomplete archives, case-changed entry points |
| [Review package](../packages/shared/.apm/skills/kit-agent-runtime/assets/review_package.py) | Require acceptance criteria; reject traversal, including rename sources |
| [Native rendering](../scripts/render_native.py) | Reject aliases, unowned collisions, edited output, extra roles |
| [Session entry](../scripts/checks/native.py) | Advisory only; no installs or authorization |
| [CI governance](../scripts/checks/governance/__init__.py) | Audit before install; reject weakened ref, review, status, timeout contracts |
| [Template checks](../tests/unit/repo_guards/test_template_toolchains.py) | Resolve symbols in their declared module |
| [YAML checks](../tests/unit/repo_guards/test_structured_templates.py) | Compare decoded key identity |
| [Feedback loop](../packages/shared/.apm/skills/kit-feedback-loop/SKILL.md) | COMPLETE, ITERATE and BLOCKED differ; missing access is not a pass |

## 9. Evaluation

[Repository evaluation cases and instructions](../tests/evals/README.md) define
synthetic positive, negative and boundary tasks; the cases themselves are not
observations. The checker validates result completeness only: it does not run a
model, authenticate observations or prove an improvement. For behavior claims,
compare baseline and candidate in the relevant named host and version, use
held-out cases where possible, and report all attempts. Unknown evidence remains
unverified. No unreviewed auto-tuning, paid run or production data.
Record resource limits and execution budgets alongside model and host versions;
report infrastructure failures separately without dropping failed attempts.
The [feedback review sources](sources.md#feedback-and-hygiene-review-2026-11-04)
ground these controls, not a claim of improved model performance.

## 10. Evidence levels

| Evidence | Establishes | Does not establish |
| --- | --- | --- |
| Primary documentation | Contract at review time | Support in an older pinned runtime |
| Source inspection | Configuration and code paths | Successful execution |
| Deterministic tests | Tested outcomes | Every environment or model |
| Real APM smoke | Install, compile, audit, delivered bytes | IDE discovery, prompts, MCP auth |
| Named native session | Observed host/version behavior | Other hosts or accounts |
| Hosted operator check | Actual protection | Enforcement from committed YAML |

## 11. Host and operator boundaries

Every role can read and run offline checks. Reviewers get no edit or delegation
tools, but a shell can still write files or reach the network; tool lists are
not a sandbox. Copilot and Claude differ in discovery, hooks and permissions;
extension agents are not ours to hide (see [editor setup](editor.md)).
Publication, required checks, bypasses, tags and authentication are operator
work: see [GitHub setup](github-setup.md), [compatibility](compatibility.md) and
[verification](verification.md).

## 12. Verification and execution notes

- Gates: `task verify` and `task apm:smoke` after the final edits; report exact
  output and any unavailable host or hosted check.
- Worker path assignments are not filesystem isolation. A 2026-10-28 research
  scratch cleanup deleted tracked documents; only known baseline files were
  restored and checked byte-identical. Keep scratch work in an explicit
  disposable directory and clean only named, owned artifacts.
