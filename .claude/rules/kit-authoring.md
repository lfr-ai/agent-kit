---
paths:
  - ".apm/**"
  - "packages/**"
  - "catalog.json"
  - "apm*.yml"
  - ".github/**"
  - ".claude/**"
---

- Maintain one authoring source; never edit generated runtime projections by hand.
- Separate portable procedure text from native tools, models, and permissions.
- Select capabilities explicitly. Install only the packages a project needs; each carries its own reviewed hooks and MCP servers.
- Validate names, resource links, ownership, scopes, and provenance before deployment.
- Fail on unknown policy fields; unsupported semantics are explicit limitations.
- Keep consumer facts and secrets in the consumer, not the toolkit.
- Verify relocation, removal, rollback, and negative cases with synthetic fixtures.
- Check existing deployed output before regenerating it.
