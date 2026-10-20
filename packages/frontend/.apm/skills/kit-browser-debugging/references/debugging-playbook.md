# Browser debugging playbook

Work from symptom to evidence to cause. Write each observation in the
[evidence record](../assets/browser-evidence.md) before forming a hypothesis.

## Symptom to first evidence

| Symptom | First place to look | Evidence to capture |
| --- | --- | --- |
| Blank page or crash | console: first uncaught error and its stack (with source maps) | error name, message, top application frame |
| Wrong or stale data | network: request URL, status, response body, cache headers | request/response pair, `Cache-Control`, `Age`, service worker involvement |
| Action does nothing | elements: is the control the event target? console for errors; React DevTools for props | handler attached, `disabled`/`aria-disabled`, overlay intercepting clicks |
| Works after reload only | application tab: storage, service worker, cached config; network "Disable cache" comparison | storage keys and values (redacted), worker version |
| Layout broken | elements: computed styles, box model, container and media queries | viewport size, zoom, computed values for the broken element |
| Slow interaction | performance panel recording; React Profiler for re-render cost | long tasks, interaction latency, components re-rendering |
| Memory growth | memory panel: heap snapshots before and after repeating a flow | retained objects, detached DOM nodes, listener counts |
| Focus lost or trapped | elements: `document.activeElement` (live expression); accessibility tree | focus sequence, element removed while focused |
| Hydration mismatch (server-rendered apps) | console warning with the differing text or attribute | server HTML versus client render for that node |
| Only in one browser | compare feature support and console in both | browser versions, feature detection results |

## Network checks

- Status and redirects: 401 versus 403 versus 404 mean different fixes.
- Response shape: compare with the schema; a 200 with an HTML error page means a
  routing or proxy fallback, not an API success.
- CORS failures appear as network errors in code; the console names the missing
  header. Fix on the server, never by disabling checks in the client.
- Caching: `Cache-Control`, `ETag`, and service worker responses explain stale
  assets after deploys (old `index.html` referencing removed chunks causes lazy
  route load failures).
- Order: compare request start and finish times when data looks stale; an older
  response finishing last indicates a race.

## React-specific checks

- React DevTools Components: inspect props, state, hooks, and the owner chain of
  the misbehaving component.
- React DevTools Profiler: record the interaction; look for components that
  re-render without prop changes and for expensive commits.
- Strict Mode double effects in development reveal missing cleanup; do not
  "fix" them by disabling Strict Mode.
- Keys: a list item keeping the wrong state after reorder means index keys.
- Effects firing in loops: inspect dependency arrays for objects recreated each
  render.

## Performance

1. Reproduce with CPU throttling (4x) and a network profile matching users.
2. Record a performance trace of the single slow interaction.
3. Identify long tasks over 50 ms; open their call trees.
4. Classify: script (expensive render, large JSON parse), style and layout
   (layout thrashing, huge DOM), or network (waterfall).
5. Fix the dominant cost, re-record, compare.

Field metrics (Interaction to Next Paint, Largest Contentful Paint, Cumulative
Layout Shift) come from real users; lab traces explain them but do not replace
them.

## Memory leaks

1. Take a heap snapshot, run the suspect flow (open and close a dialog) ten times,
   force garbage collection, take another snapshot.
2. Compare: objects growing in proportion to repetitions are leaking.
3. Typical causes: subscriptions or timers without cleanup, listeners on `window`
   not removed, caches without limits, detached DOM retained by closures.

## Reproducing in an automated test

- Encode the minimal steps in a Playwright spec using the
  [capture template](../assets/capture-evidence.spec.ts.template); it records
  console errors, page errors, failed and slow requests, and timing.
- Keep the trace (`trace: "on"` for the reproduction only) and attach it to the
  report after checking it for personal data.
- After fixing, move the essential assertion to the cheapest layer that can
  observe the fault and keep the reproduction only if it adds coverage.

## Hypothesis discipline

- One hypothesis at a time; predict what evidence would confirm or refute it.
- Change one variable per experiment (browser, data, flag, build).
- Stop and re-read the evidence when two experiments contradict each other.
- A fix is confirmed when the original reproduction passes and nearby negative
  cases still behave correctly.

## Sources

- Chrome DevTools documentation: <https://developer.chrome.com/docs/devtools>
- Chrome DevTools, network reference: <https://developer.chrome.com/docs/devtools/network/reference>
- Chrome DevTools, performance panel: <https://developer.chrome.com/docs/devtools/performance>
- Chrome DevTools, memory problems: <https://developer.chrome.com/docs/devtools/memory-problems>
- Firefox DevTools user docs: <https://firefox-source-docs.mozilla.org/devtools-user/>
- React Developer Tools: <https://react.dev/learn/react-developer-tools>
- React, `<Profiler>`: <https://react.dev/reference/react/Profiler>
- web.dev, Interaction to Next Paint: <https://web.dev/articles/inp>
- MDN, Performance API: <https://developer.mozilla.org/en-US/docs/Web/API/Performance_API>
- Playwright, trace viewer: <https://playwright.dev/docs/trace-viewer>
