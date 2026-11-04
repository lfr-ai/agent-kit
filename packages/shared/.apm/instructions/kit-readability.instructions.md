---
description: Apply to source code readability and cognitive load for reviewers and maintainers.
applyTo: "**/*.py,**/*.ts,**/*.tsx,**/*.js,**/*.jsx"
---

- Prefer the simplest behavior-complete solution; prioritize maintainability,
  readability and low cognitive load over cleverness or the fewest lines.
- Name files and symbols by domain responsibility; follow project casing and grouping, not one class per file.
- Keep one level of abstraction per function; extract a named helper when a block needs a comment to say what it does.
- Prefer guard clauses and early returns over nesting deeper than about three levels.
- Keep parameter lists short; group related values in a typed record, and replace boolean flag parameters with separate functions or an enum.
- Replace magic numbers and strings with named constants that state units and intent.
- Make data flow explicit: avoid hidden mutation of arguments, module-level state, and action at a distance.
- Prefer plain control flow over clever one-liners, nested comprehensions, or chained conditional expressions.
- Keep related code close; centralize by semantic ownership. Add folders or wrappers only for demonstrated cohesion, reuse or boundaries.
- Prefer single-line comments and simple docstrings; comment why a non-obvious decision exists, never what the code already says.
- Keep functions and modules small enough to review in one pass; split by responsibility, not line count alone.
- Use the `kit-refactor` skill when reducing complexity in existing code.
- Apply the project's naming, typing, docstring, complexity and architecture gates;
  document manual review or unavailable checks instead of claiming tool enforcement.
