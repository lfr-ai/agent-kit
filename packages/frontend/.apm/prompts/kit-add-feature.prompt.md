---
description: Build a typed, accessible React feature slice with every UI state, behavior tests first, a clear state owner, and import boundaries checked.
argument-hint: The feature and its user outcome, e.g. "list and filter invoices"
agent: agent
---

# Add a frontend feature

Deliver one user-visible feature as a self-contained slice: data boundary,
state, UI, and tests, with every state designed rather than discovered.

## Input

- The user-supplied argument describes the feature and its outcome. Ask for
  the receiving API contract and the empty and error behavior if they are not
  stated and the codebase does not imply them.

## Procedure

1. Load [kit-react-feature](../skills/kit-react-feature/SKILL.md) and fill its
   feature acceptance worksheet before editing.
2. Inspect the installed React version, rendering mode, router, data layer,
   component library, and test harness. Follow existing feature folders.
3. Define user-visible outcomes and every state: initial, loading, empty,
   partial, success, validation error, request error, and denied.
4. Decide state ownership with [kit-state-data](../skills/kit-state-data/SKILL.md):
   remote data in the query layer, URL state in the router, drafts locally.
5. Parse API responses with a schema in the feature's API module; never trust
   response shapes in components.
6. Write behavior tests first with the installed harness, querying by role and
   accessible name. Cover rejected, empty, malformed, racing, and retry cases.
7. Build from existing primitives in
   [kit-component-library](../skills/kit-component-library/SKILL.md); add a new
   primitive only when no existing one fits.
8. Use effects only to synchronize with external systems, with cleanup and
   protection against stale results.
9. Check keyboard paths, focus, announcements, contrast, and reduced motion
   with [kit-accessibility](../skills/kit-accessibility/SKILL.md).
10. Run the type checker, lint, component tests, and the skill's import
    boundary checker on the feature folder.
11. Do not install new dependencies without approval; report any you believe
    are needed.

## Acceptance gates

- [ ] Every listed state renders and has a test.
- [ ] One owner per piece of state; no effect-driven copies of server data.
- [ ] Keyboard-only use completes the primary task.
- [ ] Type, lint, test, and import boundary checks pass.

## Output

The state table (state, trigger, rendering, test), files changed, commands run
with results, and checks that need a real browser or real API.
