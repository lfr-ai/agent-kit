# Bounded React feature implementation

## Verification prerequisites

- Confirm React is actually present, its version, package manager, routing,
  rendering mode (client/server/hydrated), existing data layer and tests.
  This skill does not justify adding React to a non-React repository.
- Inspect a neighboring feature, shared primitives, localization, typed adapter
  boundary and public API contracts before choosing files.
- Define one user task and a synthetic acceptance fixture. Record available
  compiler, component runner and browser environment; missing tools are limits,
  not permission to install or create a new application.

## Design and implementation gates

| Decision | Required evidence |
| --- | --- |
| Slice | One task has an observable start, completion and failure/recovery outcome; backend and routing scope are explicit. |
| State | Server/cache, URL and local draft/interaction state each have one owner; render-derived values are not mirrored by effects. |
| Data boundary | Transport values are validated before domain/UI use; errors and empty results have deliberate representations. |
| Event logic | User-triggered work begins in the relevant action handler or existing framework mechanism, not a render side effect. |
| Effects | Only external synchronization uses effects; dependencies are truthful and subscription/timer/network ownership has cleanup. |
| Semantics | Existing native controls/primitives retain labels, keyboard behavior, visible focus, error association and status feedback. |
| Rendering | Stable identity/keys preserve the intended draft; list reorder or route change does not accidentally reset or transfer user input. |

Use the installed framework's loader/query mechanism for data where available;
do not add effect-based fetch waterfalls beside an existing cache. Do not copy
props to local state without an explicit draft/reset contract. Optimize only
after measuring a concrete bottleneck; memoization is not a correctness repair.

## Failure modes and negative cases

- Hold loading long enough to inspect feedback, then return empty, malformed,
  denied, or rejected data. No state should render a misleading success.
- Submit twice, fail once, then retry. Preserve drafts and explain ambiguous
  server outcomes; client duplicate guards do not establish idempotency.
- Change the input while request A is pending; complete newer B before A. Old
  results cannot overwrite B or show an error for the wrong selection.
- Leave the route, close a dialog, or switch identity before work finishes.
  Dispose owned subscriptions and ignore obsolete completion/focus changes.
- Reorder a list containing inputs. Stable keys must keep state with its entity,
  not with an array position.
- Under the project's Strict Mode configuration, repeated development
  setup/cleanup exposes leaks. Do not suppress it or use a "run once" ref to hide
  missing cleanup.
- For hydrated rendering, verify initial server/client output compatibility and
  keep browser-only APIs out of server execution. Do not silence hydration
  warnings as a substitute for finding nondeterminism.

## Recovery and verification

1. Fill the [acceptance slice](../assets/feature-acceptance.md); write the smallest
   observable regression before modifying the owning behavior.
2. Keep the change local. If a primitive lacks a contract, extend only the
   required behavior; do not introduce a new state manager or component system.
3. Run existing focused component tests and compiler/lint checks. Distinguish
   their evidence from browser layout, navigation, hydration and AT behavior.
4. Exercise the primary flow plus the failure/retry and disposal sequence in the
   approved browser environment when available.
5. If the change breaks a caller, repair the public contract or revert the
   bounded slice; never weaken validation, hide errors, or disable Strict Mode.
6. Report commands/results, changed boundaries, and unavailable runtime checks.

## Primary official sources

- React state structure: <https://react.dev/learn/choosing-the-state-structure>
- React effects and cleanup: <https://react.dev/learn/synchronizing-with-effects>
- React avoiding unnecessary effects: <https://react.dev/learn/you-might-not-need-an-effect>
- React state identity: <https://react.dev/learn/preserving-and-resetting-state>
- React hydration contract: <https://react.dev/reference/react-dom/client/hydrateRoot>
