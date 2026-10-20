---
description: Apply to TypeScript source and type declarations.
applyTo: "**/*.ts,**/*.tsx"
---

- Keep strict compiler checks enabled and model absent values explicitly.
- Parse untrusted JSON and URL data at the boundary with a schema; a TypeScript type does not validate runtime input.
- Prefer narrow and discriminated unions and concrete return types over `any`, non-null assertions, or broad type assertions.
- Use `unknown` for values of unknown shape and narrow them with type guards.
- Handle every member of a discriminated union and enforce exhaustiveness with a `never` check.
- Use `readonly` for data that must not change and `as const` for literal tables.
- Export explicit types at public module boundaries and keep internal helpers unexported.
- Use `import type` for type-only imports and avoid circular module dependencies.
- Keep server-only values and provider details out of browser bundles.
- Await or explicitly handle every promise; leave no floating promises or unhandled rejections.
- Avoid duplicated state and effects when a derived value or existing query layer is sufficient.
- Test invalid inputs and async failure behavior as well as the success path.
