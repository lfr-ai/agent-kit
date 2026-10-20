---
description: Apply to scenario.md files used to describe change requirements.
applyTo: "**/scenario.md"
---

- Describe one observable behavior per scenario with explicit context, action, and outcome (Given, When, Then).
- Use domain language and concrete synthetic examples that distinguish accepted behavior from nearby failure cases.
- Keep scenarios independent of implementation names, internal call order, layout details, and tool commands.
- Let each scenario set up its own context; never depend on another scenario's result.
- Cover rejection, boundary, and recovery behavior when it changes the user-visible contract.
- Give each scenario a stable, descriptive title that tests and reviews can reference.
- Use example tables for variations of one rule instead of near-duplicate scenarios.
- Write testable requirements with measurable limits; avoid vague terms such as "fast", "intuitive", or "etc.".
- Link scenarios to the change they constrain and update them in the same change when decisions change.
- Map every scenario to at least one automated test or an explicit manual verification note.
- Validate scenario syntax with the installed project tooling when available.
- Use the `kit-spec-workflow` skill for the specification procedure.
