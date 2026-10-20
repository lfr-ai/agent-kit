---
description: Apply to Bicep templates and parameter files.
applyTo: "**/*.bicep,**/*.bicepparam"
---

- Pin or constrain module sources according to the repository's supply-chain policy.
- Use current, non-preview resource API versions unless a documented preview feature is required.
- Type parameters and constrain them with decorators (`@allowed`, `@minLength`, `@description`); mark secrets `@secure()` and never give them defaults.
- Keep secret values out of outputs, defaults, and committed parameter files; reference a key vault instead.
- Derive names from parameters and `uniqueString()` with a documented convention; keep environment differences in `.bicepparam` files.
- Prefer managed identities and role assignments at the narrowest scope over keys and connection strings.
- Default to private network access, TLS 1.2 or later, and disabled public or anonymous endpoints unless explicitly required.
- Set diagnostic settings and retention explicitly for resources that support them.
- Reference resources owned elsewhere with `existing` instead of redeclaring them.
- Review scope, identity grants, network exposure, replacement, and deletion effects.
- Run offline build and lint checks before any approved preview such as what-if.
- Do not deploy or obtain cloud credentials during source authoring.
- Use the `kit-azure-validation` skill for validation steps.
