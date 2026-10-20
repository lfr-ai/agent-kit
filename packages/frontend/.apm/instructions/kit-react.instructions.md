---
description: Apply to React components, hooks, and JSX.
applyTo: "**/*.tsx,**/*.jsx"
---

- Keep components focused on one meaningful interaction or presentation responsibility.
- Follow the rules of hooks; effects synchronize with external systems, not computed state.
- Derive values during render instead of mirroring props or other state through `useState` and an effect.
- Give list items stable keys from data identity, never array indexes for lists that reorder.
- Keep render pure: no side effects, mutations, or random values in the render path.
- Clean up subscriptions, timers, and observers when their owner unmounts or inputs change; keep effects correct under Strict Mode double invocation.
- Lift state only to the nearest common owner; use context for stable cross-cutting values, not rapidly changing data.
- Memoize (`useMemo`, `useCallback`, `memo`) only for measured cost or referential contracts.
- Use semantic elements and preserve keyboard, focus, and accessible-name behavior; manage focus after dialogs and route changes.
- Model pending, empty, error, and success states explicitly for asynchronous work, with error boundaries around feature roots.
- Associate labels with form inputs and announce validation errors.
- Prefer user-visible assertions and accessible locators in component tests.
- Use the `kit-react-feature` skill for component and hook procedures.
