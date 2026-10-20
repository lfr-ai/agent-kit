---
description: Apply when a code change alters public commands, configuration, interfaces, or behavior that documentation describes.
applyTo: "**/pyproject.toml,**/package.json,**/.env.example,**/cli/**,**/cli.py,**/routes/**,**/openapi*,**/settings*.py,**/config/**,Taskfile.yml,Makefile"
---

- Treat documentation as part of the change: update it in the same change set as the behavior it describes.
- When a command, flag, environment variable, setting, default, route, or output format changes, search docs, READMEs, examples, and help text for the old value and update every hit.
- Update the changelog or release notes when the project keeps them, describing the user-visible effect rather than the implementation.
- Add an upgrade note for breaking changes with the old form, the new form, and how to find affected usage.
- Keep `.env.example` and configuration references in sync with the settings code; never add real values.
- Regenerate generated references (API schemas, CLI help, configuration tables) with the project's tool instead of editing output.
- Do not document internal refactors that leave observable behavior unchanged.
- Remove documentation for deleted features instead of leaving it marked obsolete indefinitely.
- Report which documents were updated and which related documents were deliberately left unchanged.
