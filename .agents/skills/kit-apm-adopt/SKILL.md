---
name: kit-apm-adopt
description: Use when adopting an APM capability profile in a new or existing repository.
license: MIT
---

# Adopt an APM profile

1. Inventory the consumer's actual toolchain, runtime, existing skills, hooks, and owners.
2. Select shared, backend, frontend, or fullstack; add only needed optional features.
3. Review current name collisions and preserve intentional local guidance.
4. Compose selected source into a new staging directory. Never overwrite a consumer.
5. Check provenance and the explicit local policy before running APM.
6. Install and compile with the pinned CLI; suppress lifecycle scripts.
7. Compare effective discovery and behavior, not only emitted files.
8. Publish or copy outputs only through a reviewed operator workflow.
9. Retain the prior lock, source revision, and rollback instructions.
10. Complete the [adoption gates](references/guide.md) and
    [adoption record](assets/adoption.md.template); do not confuse delivered
    templates with configured consumer knowledge, guards, or integrations.

Do not invoke global installation automatically. APM's local policy file is not
universally discovered; use the explicit audit gate.

Consumer context starting points:

- [Project facts](assets/PROJECT.template.md)
- [Agent index](assets/llms.template.txt)
- [Policy](assets/apm-policy.yml.template)
