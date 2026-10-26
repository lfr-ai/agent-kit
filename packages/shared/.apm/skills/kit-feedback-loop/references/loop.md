# The self-review and feedback loop

Reviewed: 2026-10-23.

An agent that finishes edits and immediately reports success hands its
reviewer the work of finding what it missed. A short, bounded loop catches
most of that cheaply: re-read the rules, run the deterministic checks,
compare with the acceptance criteria, and only then decide to iterate or
stop. The loop is bounded because unbounded self-revision drifts into
rewriting working code and burning budget.

## Order of evidence

| Rank | Source | Why |
| --- | --- | --- |
| 1 | Deterministic checker output (format, lint, types, conventions, architecture, tests) | repeatable, cheap, no judgment |
| 2 | Acceptance criteria with their proving tests | defines done |
| 3 | Re-read instructions and skills for the changed paths | rules the checkers do not encode |
| 4 | Inspection with `path:line` citations | judgment, must be specific |
| 5 | General preference | not a reason to iterate |

A finding from a lower rank never overrides a passing check from a higher
rank without new evidence; it becomes a proposal instead.

## Re-read the governing rules

- Open the operating policy and every scoped instruction whose glob matches a
  changed path. Do not rely on what you remember from the start of the task;
  long tasks lose early context.
- Re-open the procedure and acceptance gates of each skill used.
- Write the rules as a short checklist. Mark which ones a tool verifies and
  which need inspection.

## Convention re-check

Run the project's own checkers before reading code by eye. Typical mapping:

| Convention | Prefer this check | Inspect when no check exists |
| --- | --- | --- |
| Naming | linter naming rules, naming checker | names state meaning and unit |
| Magic numbers | linter or convention checker for unnamed literals | literals other than 0 and 1 are named constants |
| Docstrings | docstring linter | public symbols document arguments, returns, raises |
| Typing | type checker in strict mode | no `Any`, casts or untyped public functions |
| Layering | architecture or import-boundary check | dependencies point inward; I/O at the edges |
| Errors | linter exception rules | specific exceptions, chained causes, no silent catch |
| Tests | focused test run, coverage of changed lines | a failing path is tested, not only the happy path |
| Docs | link and spelling checks | changed behavior is reflected where it is documented |

## Simplify and check currency

Ask, for the final diff:

1. Can any new helper, class, flag or configuration be deleted with no
   failing test? Delete it.
2. Does the standard library or an already-locked dependency do this? Use it.
3. Is there a newer, officially recommended tool or API for this task in the
   current documentation of the language, framework or host? Check the
   official source and its date; do not rely on training memory.
4. Is the change larger than the request? Split out or drop the extra part.

Adopting a newer tool or dependency is a separate, approved change, not a
side effect of a review loop. Record the proposal and its source instead.

## Iterate or stop

| Situation | Decision |
| --- | --- |
| A checker fails on a changed file | iterate; fix the cause, not the check |
| An acceptance criterion is unmet or partial | iterate if inside scope; otherwise stop and report |
| A required convention is violated (inspection, cited) | iterate |
| A simpler equivalent exists and is local | iterate once to adopt it |
| Only style preferences remain | stop |
| The same finding returns after a fix | stop; report it with evidence, request a decision |
| The budget is spent | stop; report remaining findings by severity |
| The fix needs files outside the owned scope | stop; report it as a follow-up |

Severity order for fixes: correctness and security, contract and data
compatibility, required conventions, tests and documentation, then
simplification.

## Recording lessons

At the end of the loop, ask which surprise would have saved time if known at
the start. Record it only if it is durable, evidenced and not already
enforced, through the `kit-project-memory` skill. A lesson that can become a
check should become a check.

## Failure modes

| Symptom | Cause | Response |
| --- | --- | --- |
| Loop never ends | no budget or stop condition | set both before the first review |
| Review approves a failing build | checks not re-run after the last edit | run checks last, then report |
| Each iteration rewrites unrelated code | scope creep | revert out-of-scope edits; log as follow-up |
| Weakened assertion or raised threshold to pass | optimizing for green | restore it; fix the cause |
| Generic findings ("could be cleaner") | no citations | require `path:line` and the violated rule |
| Lessons file grows every task | recording activity, not knowledge | apply the evidence and durability bar |

## Primary sources

- [Anthropic: building effective agents (evaluator-optimizer loop)](https://www.anthropic.com/engineering/building-effective-agents)
- [Anthropic: Claude Code best practices](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Anthropic: effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Google SRE book: postmortem culture](https://sre.google/sre-book/postmortem-culture/)
