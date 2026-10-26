---
description: Apply when writing or editing agent prompt files, instructions, skills, agent roles, or entry files such as AGENTS.md and CLAUDE.md.
applyTo: "**/*.prompt.md,**/*.instructions.md,**/SKILL.md,**/*.agent.md,**/AGENTS.md,**/CLAUDE.md"
---

- Make user-invoked workflows prompt files and roles that need their own tools or context agents; keep both short.
- Keep a prompt file to inputs, steps, gates and output, and link the skill that owns the procedure instead of restating it.
- Measure the characters of always-on content; do not claim token, latency or cost savings without a host measurement.
- Write descriptions in the requester's words and name what distinguishes the item from its neighbors.
- Keep volatile values such as dates, versions and task details out of always-on files so their text stays stable.
- Do not pin model names or grant native tools in portable text; leave them to host configuration.
- Use the `kit-context-engineering` skill for budgets and placement, and `kit-project-memory` for decisions and lessons.
