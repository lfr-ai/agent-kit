---
description: Apply to agent instructions, runtime settings, hooks, and portable capability metadata.
applyTo: "AGENTS.md,CLAUDE.md,.github/copilot-instructions.md,.claude/**,.apm/**,**/*.instructions.md,**/SKILL.md,**/*.agent.md"
---

- Keep portable guidance separate from native runtime permissions, models, tools, and hooks.
- Use only fields and glob syntax the target runtime version documents; treat unknown fields as errors, not hints.
- Treat instructions as advisory; do not claim they enforce access, isolation, or approval.
- Scope each instruction file with the narrowest `applyTo` glob that matches its files; reserve `**` for one short safety file.
- Keep instructions to always-true rules; move procedures, examples, and long references into skills.
- Give each skill a `name` equal to its folder and a single-line `description` that starts with "Use when".
- Keep skill resources inside the skill folder and reach them through relative links that resolve.
- Avoid duplicated policy across instructions, skills, and agent roles; link the owner instead.
- Never embed secrets, personal data, private host names, or consumer facts in portable configuration.
- Never edit generated projections by hand; change the source and recompose.
- Grant tools, network, and shell access per role by least privilege; keep destructive tools behind approval.
- Test composition or parsing with a disposable fixture when available.
- Never modify user-global settings or enable side effects as an implicit default.
