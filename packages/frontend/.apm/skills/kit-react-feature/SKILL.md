---
name: kit-react-feature
description: Use when building or reviewing an accessible typed React feature and its tests.
license: MIT
---

# Implement a frontend feature

## Resources

- [Feature implementation guide](references/guide.md): prerequisites, ownership
  gates, failure modes, recovery.
- [Feature folder architecture](references/feature-architecture.md): layout,
  dependency rules, placement decisions, anti-patterns.
- [React 19 patterns](references/react19-patterns.md): actions, optimistic UI,
  `use`, refs, effects, derived state.
- [Feature acceptance slice](assets/feature-acceptance.md) to fill per task.
- Templates: [public index](assets/index.ts.template),
  [model](assets/order.model.ts.template),
  [list component](assets/order-list.tsx.template) with
  [behavior test](assets/order-list.test.tsx.template),
  [strict tsconfig](assets/tsconfig.json.template),
  [Vite config](assets/vite.config.ts.template).
- Checker: [feature import boundaries](assets/check_feature_imports.py)
  (`--root`, `--alias`, `--shared-dir`, `--self-test`).

## Procedure

1. Read the guide; fill the acceptance slice before editing.
2. Inspect the actual package, React version, rendering mode, router, data layer,
   and a neighboring feature. Do not add React or a new state manager.
3. Define user-visible outcomes, validated data boundaries, and all UI states.
4. Place code with the architecture decision guide; expose only a deliberate
   public `index.ts`.
5. Write focused behavior tests before implementation with the installed harness;
   fake the network at the HTTP boundary, not inside components.
6. Reuse accessible primitives and semantic controls; preserve keyboard and focus.
7. Keep transport adapters outside domain policy; give each state one owner.
8. Use effects only for external synchronization, with cleanup and stale-work
   handling; choose React 19 APIs only when the installed version supports them.
9. Test rejected, empty, malformed, racing, navigation-away, and retry sequences.
10. Run the type checker, component tests, lint, and the import boundary checker
    (or the project's equivalent rule); exercise a real browser where relevant.
11. Check contrast, live announcements, error recovery, and reduced motion.
12. Report exact commands, results, and unavailable checks. Do not install
    frontend tools implicitly; this capability supplies procedure and templates,
    not an application or runtime certification.

## Acceptance gates

- [ ] Pending, error-with-retry, empty, success, and malformed-data states each
      have a behavior test.
- [ ] Transport data is parsed by a schema before UI use; no type assertions.
- [ ] Other modules import the feature only through its public index.
- [ ] Every effect has cleanup and survives the Strict Mode development cycle.
- [ ] Keyboard-only use, visible focus, and announced status were verified.
- [ ] Strict compiler, lint, and focused tests pass with exact output reported.
