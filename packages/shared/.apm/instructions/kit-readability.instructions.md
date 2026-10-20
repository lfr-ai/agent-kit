---
description: Apply to source code readability and cognitive load for reviewers and maintainers.
applyTo: "**/*.py,**/*.ts,**/*.tsx,**/*.js,**/*.jsx"
---

- Optimize for the next reader: a function should be understandable without opening more than one or two other files.
- Name values, functions, and types after what they mean in the domain, not their type or implementation.
- Keep one level of abstraction per function; extract a named helper when a block needs a comment to say what it does.
- Prefer guard clauses and early returns over nesting deeper than about three levels.
- Keep parameter lists short; group related values in a typed record, and replace boolean flag parameters with separate functions or an enum.
- Replace magic numbers and strings with named constants that state units and intent.
- Make data flow explicit: avoid hidden mutation of arguments, module-level state, and action at a distance.
- Prefer plain control flow over clever one-liners, nested comprehensions, or chained conditional expressions.
- Keep related code close; avoid indirection layers, factories, or inheritance that have only one implementation.
- Comment why a non-obvious decision exists; do not narrate what the code already says.
- Keep functions and modules small enough to review in one pass; split by responsibility, not line count alone.
- Use the `kit-refactor` skill when reducing complexity in existing code.
