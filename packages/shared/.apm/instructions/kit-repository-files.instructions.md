---
description: Apply to community health files, pull request and issue templates, and environment example files.
applyTo: "README.md,CONTRIBUTING.md,SECURITY.md,.env.example,**/.env.example,.github/**/*.md"
---

- Write plainly for a first-time reader: no emojis, marketing claims, or badge walls; put the README quick start before background.
- Copy every command, flag, version, and default from its source of truth, and run it or label it illustrative.
- Use the project's own names and role-based contacts; never leave another project's name, a placeholder, or a personal address in a published file.
- Route vulnerability reports to a private channel; never ask reporters to open a public issue.
- In `.env.example`, list every variable the code reads, each with a comment above it, grouped by concern, with placeholder or harmless local values only.
- Never put real keys, passwords, tokens, internal host names, or personal data in these files.
- Keep pull request templates and contribution steps consistent with the repository's actual gate and commit conventions.
- Use the `kit-repository-setup` skill for adding or auditing these files.
