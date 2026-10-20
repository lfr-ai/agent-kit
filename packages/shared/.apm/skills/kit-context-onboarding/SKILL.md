---
name: kit-context-onboarding
description: Use when entering an unfamiliar repository or bounded subsystem before proposing changes.
license: MIT
---

# Establish working context

## Procedure

1. Read the operating policy, project facts, package manifest and declared
   verification commands. Know each entry file's job from
   [entry files](references/entry-files.md).
2. Follow the [30-minute onboarding route](references/onboarding.md): toolchain
   and gate, structure map, one traced call path, boundaries and gaps. Stay
   read-only until the outcome and allowed files are clear.
3. Identify the owning package, entry points, tests and nearby examples for the
   requested behavior, and check whether target files are generated, vendored
   or owned by another package.
4. Search for existing helpers and contracts before introducing a parallel
   abstraction.
5. Separate observed facts from assumptions; record missing tools,
   inaccessible dependencies and anything you could not run.
6. When the consumer lacks entry files, start from the
   [policy](assets/AGENTS.md.template), [project facts](assets/PROJECT.md.template),
   [context entry](assets/llms.txt.template), [package inventory](assets/projects.md.template)
   and [knowledge index](assets/knowledge-index.md.template) templates, merged
   with existing owned guidance rather than overwriting it.
7. Run the read-only [context checker](assets/check_context.py) with `--root`
   (and repeated `--entry` for other names). It checks files and links, not
   factual accuracy.
8. Structure durable knowledge as in [knowledge base and freshness](references/knowledge-base.md),
   recording lessons with the [memory entry template](assets/memory-entry.md.template).
9. Run the [memory freshness checker](assets/check_memory_freshness.py) over
   memory and decision folders with an agreed `--max-age-days`; re-verify,
   update or supersede every flagged entry.
10. At the end of the task, run the [self-reflection loop](references/self-reflection.md)
    and put each lesson in its single owning place, preferring a check over prose.
11. Ask for clarification when ownership or a destructive consequence cannot be
    resolved locally.

The [context map](references/guide.md) summarizes ownership and lifetimes.

## Acceptance gates

- The install, focused test and completion commands were run or explicitly
  reported as unavailable, with working directory.
- One call path for the requested behavior is mapped to `file:function` steps
  and its nearest test.
- Both checkers exit 0, or every finding is listed with its resolution.
- New memory entries are dated, evidenced, scoped and free of credentials,
  personal data and transcripts.
- No private repository facts were copied into portable bundles.
