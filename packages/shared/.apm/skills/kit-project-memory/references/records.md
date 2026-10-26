# Records, lessons, plans and freshness

Reviewed: 2026-10-23.

## Decision records (MADR style)

One decision per file under the decisions folder, numbered `NNNN-title.md`
and never renumbered. Start from the [record template](../assets/adr.md.template),
which follows the Markdown Architectural Decision Records layout: context and
problem, decision drivers, considered options, outcome, consequences,
confirmation and per-option pros and cons. This is the single decision record
template; the `kit-documentation` skill links explanation pages to records
written with it.

Status values and transitions:

| Status | Meaning | Next |
| --- | --- | --- |
| `proposed` | under discussion, not yet binding | `accepted` or `rejected` |
| `accepted` | binding until replaced | `deprecated` or `superseded` |
| `rejected` | considered and declined; kept so it is not re-proposed blindly | none |
| `deprecated` | no longer recommended, no direct replacement | none |
| `superseded` | replaced by a named record | none |

Supersession rules:

- Write a new record; never edit the decision of an accepted record.
- The old record gets `status: superseded` and a `superseded-by` link; the new
  record lists `supersedes` with a link back.
- Corrections of typos or broken links are allowed edits; changes of meaning
  are not.

A record earns its place when the decision is costly to reverse, affects more
than one component, or was contested. Routine choices go into code review.

## Lessons

A lesson is a surprising, evidenced fact that would otherwise be
rediscovered. Use the [lesson template](../assets/lesson.md.template):

- heading starts with the ISO date: `## 2026-10-23 Short lesson`;
- `Status:` `active` or `superseded`;
- `Evidence:` the command, test, file or document that shows it;
- `Scope:` where it applies and where it does not;
- `Last verified:` updated each time someone re-checks it.

Prefer turning a lesson into a check. When a check enforces it, mark the
lesson superseded and link the check.

## Plans and TODOs

A plan file tracks work that spans sessions or agents. Use the
[plan tracker](../assets/plan.md.template): goal, acceptance checks, a task
table with one status per task (`todo`, `doing`, `blocked`, `done`,
`dropped`), owners by role, and decisions taken while executing. Design and
slicing belong to the `kit-change-plan` skill; the tracker links to that plan
instead of repeating it. Inline `TODO` comments in code need an issue or plan
reference, or they are deleted.

## Session handoffs

A handoff captures in-flight state so another session, agent or host can
resume without the transcript. Use the
[session handoff template](../assets/session-handoff.md.template): outcome,
state of each step, last command with its result, the next smallest action,
open questions and files touched. It is deleted when the work resumes and
finishes; durable findings move into lessons or records first. Worker-to-
coordinator handoffs inside one delegated task follow the
`kit-subagent-delivery` skill instead.

## Freshness and pruning

| Trigger | Action |
| --- | --- |
| Linked code, configuration or test changed | re-verify entries that link to it in the same change |
| Entry older than the agreed age without verification | re-run its evidence; add `Last verified:` or supersede |
| Entry contradicted by a check or a newer record | mark superseded with a link |
| Plan done or dropped | fold decisions into records, then archive or delete |
| Handoff resumed and finished | delete |
| Entry restates what code or `PROJECT.md` says | delete and link the source |

Age alone does not make an entry wrong; it makes it unreviewed.

## The memory file checker

[`check_memory_files.py`](../assets/check_memory_files.py) scans Markdown files
or folders and reports, as `path:line: message`:

- a dated entry heading (at `--entry-level`, default 2) whose date is missing,
  invalid or in the future;
- a dated entry missing a required field (`--require`, default `Status` and
  `Evidence`), or a status outside the allowed set;
- a superseded entry or record without a `Superseded by` link;
- a record with front matter (decision records) missing `status` or `date`;
- a local link that is absolute, leaves `--root`, or points to a missing file;
- an active entry whose newest date (heading, `date`, or `Last verified:`)
  is older than `--max-age-days` (default 180).

Files without dated headings or front matter are treated as indexes: only
their links are checked. Fenced code blocks and HTML comments are ignored and
web links are not fetched. Use `--today YYYY-MM-DD` for reproducible runs.
Exit status: 0 clean, 1 findings, 2 unreadable input or bad arguments. Run
`--self-test` after copying it into a project.

For repositories whose memory files are plain dated notes without `Status`
or `Evidence` fields, add `--freshness-only`: it skips required fields, the
status vocabulary, supersession links and the every-heading-dated rule, and
keeps date validity, staleness (refreshed by `Last verified:`, `Verified:` or
`Reviewed:`), the exemption of superseded entries and all link checks. Adopt
the full rules once entries follow the [lesson template](../assets/lesson.md.template).

## Anti-patterns

- Diary entries that record activity instead of knowledge.
- One incident promoted to an always-on rule before it recurs.
- The same lesson in a memory file, a skill and the policy.
- Deleting a superseded decision instead of linking its replacement.
- Storing host-private memory exports in the repository.

## Verification

1. Run the checker on every memory and decision folder.
2. Open each new entry and follow its evidence link; it must resolve and still
   show the claim.
3. Search for the entry's key terms elsewhere; remove any duplicate.
4. Confirm superseded and superseding records link each other.

## Primary sources

- [MADR: Markdown Architectural Decision Records](https://adr.github.io/madr/)
- [ADR GitHub organization](https://adr.github.io/)
- [Michael Nygard: Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [Claude Code memory](https://code.claude.com/docs/en/memory)
- [About GitHub Copilot Memory](https://docs.github.com/en/copilot/concepts/agents/copilot-memory)
