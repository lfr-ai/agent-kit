# Knowledge base structure and memory freshness

A knowledge base holds what is true about a codebase beyond what the code
itself says: why decisions were made, how to operate and recover it, and
lessons learned while working on it. It decays: code moves, decisions are
superseded, and a confident but stale note is worse than none.

## Structure

Keep the knowledge base in the repository, next to the code it describes, so
it is reviewed and versioned with that code.

```text
docs/ or .agents/knowledge-base/
  README.md              index: one row per topic, linked to owners
  architecture.md        components, dependency direction, trust boundaries
  decisions/
    0001-record-decisions.md
    0002-orders-use-event-log.md
  operations.md          run, deploy, observe, recover
memories/
  lessons.md             dated, evidenced lessons from past work
```

| Kind | Holds | Lifetime | Owner |
| --- | --- | --- | --- |
| Index | links and one-line summaries | as long as the topics exist | maintainers |
| Architecture | structure and boundaries as they are now | until the structure changes | component owners |
| Decision record | one decision, its context and consequences | permanent; superseded, never edited away | decision makers |
| Operations | runbooks, recovery, rollback | until the procedure changes | operators |
| Memory / lesson | a surprising fact learned while working, with evidence | until re-verified or superseded | whoever recorded it |
| Task hand-off | state of one unfinished task | the task | the current assignee |

Rules:

- Link to the owning code, test or configuration instead of copying values.
- One topic per file; the index makes topics discoverable.
- Never store credentials, personal data, chat transcripts or private
  customer facts. Record locations and names, not values.
- Task hand-offs are deleted or folded into durable entries when the task ends.

## Writing a memory entry

Write entries with the `kit-project-memory` skill, which owns the lesson,
decision record, plan and handoff templates. An entry earns its place only
if it is:

- **Surprising**: a future reader would likely get it wrong without it.
- **Evidenced**: it names the command, test, file or document that shows it.
- **Scoped**: it says where it applies and where it does not.
- **Dated**: the heading carries the date it was recorded, in ISO form
  (`## 2026-03-14 Exports retry only idempotent requests`).

Lessons that turn into permanent rules move into the operating policy or a
check, and the memory entry is marked superseded with a link to the new home.

## Freshness and decay

Facts decay at different rates. Re-verify when either trigger fires:

1. **Change trigger**: the code, configuration or document the entry links to
   changed. This is the strongest signal; review entries that link to files in
   a change set.
2. **Age trigger**: the entry has not been verified for longer than the
   repository's limit (for example 180 days). Age alone does not make an entry
   wrong; it makes it unreviewed.

Re-verifying means running or reading the evidence again, then either adding
a `Last verified: YYYY-MM-DD` line, editing the entry, or marking it
`Status: superseded` with a link to its replacement. Never silently delete a
decision record; supersede it.

### Checking freshness

The `kit-project-memory` skill owns the memory checker. Run it over memory
and decision folders with `--freshness-only` for plain dated notes, or with
the full rules once entries carry `Status` and `Evidence` fields. In both
modes it reports:

- dated headings whose most recent date (heading date or a later
  `Last verified:`, `Verified:` or `Reviewed:` line in that entry) is older than
  `--max-age-days` (default 180),
- dates that are invalid or in the future,
- local links that point to missing files, are absolute, or leave `--root`.

Entries marked `Status: superseded` are not aged but their links are still
checked. Fenced code blocks are ignored. Web links are not fetched.

```text
python check_memory_files.py memories docs/decisions --root . --max-age-days 120 --freshness-only
memories/lessons.md:7: entry '2025-01-01 Exports retry ...' was last verified 512 days ago (limit 120); re-verify it or mark it superseded
memories/lessons.md:9: link '../src/exports/retry.py' points to a missing file
```

Use `--today YYYY-MM-DD` for reproducible runs in CI or tests. Add the
checker to the repository's scheduled or pre-merge checks with a limit the
team agrees on. A finding is a prompt to review, not proof the entry is wrong.

## Decision records

A decision record captures one decision: context, options considered, the
decision, consequences, status (`proposed`, `accepted`, `superseded`) and
date. Number records sequentially and never reuse a number. The
`kit-project-memory` skill has the record template and supersession rules.

## Sources

- [Michael Nygard: Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [ADR GitHub organization](https://adr.github.io/)
- [Claude Code memory](https://code.claude.com/docs/en/memory)
- [Anthropic: effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
