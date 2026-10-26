---
name: kit-project-memory
description: Use when deciding where a project decision, lesson, plan or handoff persists across sessions and hosts.
license: MIT
---

# Persist project memory across agents and hosts

## Procedure

1. Classify the item before writing it: fact, rule, architecture, decision,
   lesson, plan or in-flight state. Use the placement table in
   [memory layout](references/layout.md); an item that fits no row is not
   stored.
2. Refuse to store secrets, credentials, personal data, chat transcripts,
   customer content or unverified speculation, even redacted. Store the
   location of a value, never the value.
3. Search the destination for an existing entry first. Update, re-verify or
   supersede it; never add a near-duplicate.
4. Write the item with the matching asset:
   - architecture decision: [MADR-style record](assets/adr.md.template);
   - lesson: [lesson entry](assets/lesson.md.template) with evidence;
   - multi-session work: [plan tracker](assets/plan.md.template);
   - unfinished work for the next session or host:
     [session handoff](assets/session-handoff.md.template);
   - knowledge base index: [knowledge base README](assets/knowledge-base-README.md.template).
5. Link to the owning code, test, command or document instead of copying its
   content; copies drift. Follow the record rules in
   [records and freshness](references/records.md).
6. Keep always-on entry files (`AGENTS.md`, `CLAUDE.md`, the Copilot
   instructions file) short; they point to on-demand files. Check each host's
   loading rules in [host differences](references/hosts.md) before relying on
   a host memory feature.
7. Supersede decisions and lessons by status and link; never delete or
   silently rewrite an accepted record.
8. Close out in-flight state: fold durable parts of a handoff or plan into
   records, then delete the handoff when its work is done.
9. Validate the memory files with
   [`check_memory_files.py`](assets/check_memory_files.py), for example
   `python check_memory_files.py memories docs/decisions --root . --max-age-days 180`.
   It checks dated headings, required fields, status values, supersession
   links, local links and age. Re-verify or supersede every flagged entry.
10. Route the end-of-task reflection through the `kit-feedback-loop` skill and
    project-context bootstrapping through `kit-context-onboarding`.

## Acceptance gates

- Every new item has exactly one home from the placement table, and no other
  file restates it.
- Decision records carry status and date; superseded records link their
  replacement and the replacement links back.
- Every lesson names its evidence (command, test or file) and its scope.
- Nothing stored contains credentials, personal data, transcripts or guesses
  presented as facts.
- `check_memory_files.py` exits 0, or each finding is listed with its
  resolution; `--self-test` passes after the checker is copied.
- Always-on entry files link to detail instead of embedding it, and their size
  was measured, not estimated.
