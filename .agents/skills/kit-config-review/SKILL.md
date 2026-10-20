---
name: kit-config-review
description: Use when reviewing agent instructions, skills, native permissions, hooks, or catalog growth.
license: MIT
---

# Review configuration changes

1. Locate the canonical owner and prior coverage of the behavior.
2. Separate always-on invariants, path rules, and on-demand procedures.
3. Check names against every effective installation source.
4. Compare selected runtime fields and permissions rather than assuming portability.
5. Check context footprint, resource containment, source provenance, and negative tests.
6. Reject silent fallback, duplicate hook execution, or undeclared integration startup.
7. Report changes by impact, with evidence and limits.

Prefer extending an existing procedure over adding another near-duplicate.
Keep discovery metadata short and specific; full resources load only when needed.

Use the [review matrix](references/guide.md) and
[configuration evidence](assets/review.md.template).
