---
name: kit-frontend-testing
description: Use when designing frontend tests across unit, component, integration, and browser layers.
license: MIT
---

# Choose the cheapest test that proves the behavior

## Resources

- [Layer and determinism guide](references/guide.md): failure-recovery gates.
- [Component testing patterns](references/component-testing.md): layer choice,
  query priority, interactions, assertions, network boundary, coverage,
  anti-patterns.
- [Determinism](references/determinism.md): controlled inputs, async discipline,
  deliberate races, Strict Mode, order independence.
- [Behavior-to-layer matrix](assets/test-layer-matrix.md) to fill per change.
- Templates: [Vitest config](assets/vitest.config.ts.template),
  [setup](assets/test-setup.ts.template),
  [render helper](assets/render-with-providers.tsx.template),
  [MSW helpers](assets/msw.ts.template),
  [data builder](assets/order.factory.ts.template),
  [fake-timer component](assets/debounced-search.tsx.template) with
  [tests](assets/debounced-search.test.tsx.template).

## Procedure

1. Read the guide; fill the behavior-to-layer matrix.
2. Map each contract to its owning layer: pure, hook, component, route, or browser.
3. Test reducers, mapping, and formatting as pure functions with boundary inputs.
4. Render components with the shared providers; query by role and accessible name.
5. Assert visible states, accessible names and descriptions, and focus, not
   internals or call counts of hooks.
6. Fake the network with MSW at the HTTP boundary; fail on unhandled requests.
7. Include pending, rejected, empty, malformed, and retry states users can reach.
8. Control clocks, randomness, response order, storage, and per-test cleanup.
9. Keep a small number of browser tests for high-value cross-layer contracts.
10. See each new regression fail without the fix; check types and lint separately.
11. Remove test-only production branches; inject seams instead.
12. Report exact focused commands, results, and untested browser/server boundaries.

## Acceptance gates

- [ ] Each behavior is tested at the cheapest layer that observes its failure.
- [ ] Role and label queries; no implementation selectors without justification.
- [ ] Network faked at HTTP level; unhandled requests fail.
- [ ] No real time, randomness, or network; tests pass shuffled and alone.
- [ ] Coverage thresholds pass without assertion-free tests.
