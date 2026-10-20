# Build a small, owned knowledge map

## Entry points

Read the repository policy, project facts, package manifest, and declared gate.
Follow links for the requested boundary, not every document. Record the entry
point, use case, effect adapter, error path, and nearest behavioral test.
Distinguish installed-package paths from source-checkout paths.

Keep four kinds of information separate:

| Information | Owner | Lifetime |
| --- | --- | --- |
| Invariants and approval boundaries | repository policy | until policy review |
| Commands, versions, layout | project facts | until toolchain/layout change |
| Architecture and decisions | linked knowledge index | until superseded |
| Reproduction, partial results | task handoff | current task only |

Use the [project template](../assets/PROJECT.md.template) and
[knowledge index](../assets/knowledge-index.md.template). Replace placeholders
with evidenced consumer facts. Never ship private facts back into a portable bundle.
Each durable decision needs its rationale, owning code or test, date checked,
and an explicit supersession link if replaced. Do not retain credentials or
personal transcripts in memory.

Complete the [policy template](../assets/AGENTS.md.template),
[context entry](../assets/llms.txt.template) and
[package inventory](../assets/projects.md.template) only when the consumer lacks
their equivalents. Merge with existing owned guidance rather than overwriting it.
Use the exact supported native adapter for optional imports; do not duplicate
portable policy in every provider-specific entry file.

## Quality gates

- A new reader can find one runnable owning test without reading the whole wiki.
- Every asserted command exists in the manifest/runner and has a known cwd.
- Generated files link to their authoring owner; there is no second policy tree.
- Missing tools, stale links, conflicting instructions and inaccessible sources
  are reported as unresolved, not filled with plausible guesses.
- Native/user/plugin context is inspected separately: repository files cannot
  suppress inherited instructions or tool exposure.

The portable [checker](../assets/check_context.py) accepts an explicit `--root`;
default entries are `AGENTS.md`, `PROJECT.md` and `llms.txt`. Repeated `--entry`
replaces that list when the consumer uses other entry names. Missing, empty,
escaping and broken local-link inputs return nonzero. Network links and Markdown
anchors are not fetched or validated; this is not a policy, fact or app validator.
Run `--self-test` before wiring it into the consumer's existing check runner.

## Failure and recovery

If an entry file conflicts with executable behavior, retain the failing evidence
and update the owner only after confirming intended behavior. If interrupted,
handoff the outcome, changed paths, exact test result, next check and blockers;
do not paste the complete session. Recheck facts after a relevant code change;
treat an age limit only as a review trigger, as described in
[knowledge base and freshness](knowledge-base.md).

Sources: [Claude memory](https://code.claude.com/docs/en/memory),
[context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents).
