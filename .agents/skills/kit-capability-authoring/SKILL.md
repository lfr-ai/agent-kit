---
name: kit-capability-authoring
description: Use when adding or changing a skill, instruction, agent role, bundle, or profile in this repository, or when a guard rejects such a change.
license: MIT
---

# Author a capability in the owning source

1. Search `.apm/`, `packages/*/.apm/`, and `catalog.json` for the topic first; extend or link an existing capability before adding one.
2. Choose the owner by audience: toolkit-only guidance in root `.apm/`; reusable guidance in the smallest package. Use `shared` only when every profile needs it.
3. Skill: directory name equals `name` (`kit-<topic>`). Frontmatter has only `name`, `description`, `license: MIT`. Start the description with "Use when" and state the trigger in 350 characters or fewer. Keep the body to a numbered procedure under 300 lines; put detail in `references/`, templates in `assets/`.
4. Instruction: `<name>.instructions.md` with `description` and a narrow `applyTo`. Keep it to a few bullets that are always true for those paths; procedures belong in skills.
5. Role: edit the owning skill's `assets/agents.json`. Use a unique `kit-` id, the least-privilege tier, and a short body. Workers never delegate.
6. Bundle or profile: edit `catalog.json` and the package `apm.yml` with explicit `includes`. Never raise a budget; trim or split instead.
7. Keep consumer facts, secrets, absolute paths, and company material out of portable text.
8. Add a failing synthetic test for any new validation rule. Content-only edits need none.
9. Never edit generated `.agents/skills`, `.claude/skills`, native role files, or lockfiles by hand.
10. Use the [resource contract](references/guide.md) and
    [change worksheet](assets/capability.md.template) to retain useful depth.

# Verify

1. Run `task verify -- source`; `uv run agent-kit check --root . --json` reports per-profile description totals.
2. If root `.apm/` changed, run `task verify -- drift` first, then refresh output with the pinned APM install used by `task apm:smoke`, then `task verify -- drift` again.
3. If role assets changed, run `task verify -- roles`; refresh with `uv run --locked python -m scripts.render_native --write` only for this repository's own selection.
4. Run `task verify`; run `task apm:smoke` after APM-facing changes. Use `task verify -- <gate>` for focused checks, not another one-command Task target. Keep devtool defaults unless an intentional policy override is needed.
5. Record a durable surprise in `memories/` with its evidence.
