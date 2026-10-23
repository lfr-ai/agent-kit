# Route patterns for data routers

The templates target React Router v7 or later in data mode
(`createBrowserRouter` plus `RouterProvider`). Framework mode (file routes and
server rendering) uses the same loader and boundary concepts with different
wiring; check which mode the project uses before copying.

## Building blocks

| Piece | Template |
| --- | --- |
| Route tree, layout, auth redirect, lazy routes, catch-all | [router.tsx](../assets/router.tsx.template) |
| Route module with param validation and cache-backed loader | [order-detail.route.tsx](../assets/order-detail.route.tsx.template) |
| Error boundary for 401/403/404 and unexpected errors | [route-error-boundary.tsx](../assets/route-error-boundary.tsx.template) |
| Title and focus management after navigation | [route-focus.tsx](../assets/route-focus.tsx.template) |
| URL state schema, hook, safe return path | [search-params.ts](../assets/search-params.ts.template) |
| Memory-router tests for all of the above | [router.test.tsx](../assets/router.test.tsx.template) |

URL state and history rules are in [URL state and history](url-state-and-history.md).

## Route tree shape

```text
/ (RootLayout, root ErrorBoundary = last resort)
└── pathless boundary (page errors render inside the layout)
    ├── index -> redirect("/orders")
    ├── sign-in
    ├── pathless "authenticated" (loader: requireSession)
    │   ├── orders
    │   └── orders/:orderId (loader, own ErrorBoundary)
    └── * -> 404
```

- Put an error boundary on a pathless child of the layout so navigation and
  headers survive a page failure. The root boundary handles layout failures.
- Give routes with independent failure modes their own boundary so a failing
  detail panel does not blank the list beside it.
- Lazy-load route modules with `lazy`; return `Component`, `loader`, and `action`
  from the same module so code and data load in parallel.
- Provide `HydrateFallback` on the root when loaders run on first load.

## Loaders

1. Validate params and search params with a schema first. A malformed id is a 404
   without a network request.
2. Fetch through the query cache: `queryClient.ensureQueryData(options)` returns
   cached data or fetches it, so the component's `useQuery`/`useSuspenseQuery` with
   the same options renders immediately and still refreshes in the background.
3. Translate expected API failures into route responses
   (`throw data(message, { status })`): 401, 403, 404. Let unexpected errors
   propagate to the boundary as errors.
4. Return small values (ids, parsed search) rather than whole entities when the
   component reads the cache anyway.
5. Loaders receive `request.signal`; pass it to direct fetches so abandoned
   navigations cancel. The query layer cancels its own requests.
6. Avoid waterfalls: start independent fetches in parallel with `Promise.all`;
   parent and child loaders already run in parallel.

## Actions and mutations

- With router actions (`<Form method="post">`, `useFetcher`), the router
  revalidates loaders after the action. With query-library mutations, invalidate
  the affected query keys instead; do not use both for the same data.
- Return validation errors from actions as data with a 400/422 status and render
  them in the form; throw only for unexpected failures.
- Redirect after a successful create (`redirect("/orders/" + id)`) so a reload
  does not resubmit.

## Pending and error UI

- Global navigation progress: `useNavigation().state !== "idle"` renders a
  polite status, not a full-page spinner.
- Keep the previous page visible during navigation; the new page appears when
  its loaders finish.
- Error boundaries focus their heading, explain what happened in plain words,
  offer a retry only when retrying can help (`useRevalidator().revalidate()`),
  and always offer a way out (link home or back).
- Never render stack traces or raw server messages to users.

## Access control

- Route guards (`requireSession`) are navigation aids. The API authorizes every
  request; a guard bypassed in devtools must reveal nothing.
- Redirect to sign-in with a `returnTo` that passes `safeReturnTo`: same-origin
  paths only, which prevents open redirects.
- Hide navigation entries the user cannot use, but still handle 403 on direct
  visits.

## Navigation accessibility

- Links navigate (`<Link>`, `<NavLink>`); buttons act. Never use a click handler
  on a `div` for navigation.
- `NavLink` sets `aria-current="page"` on the active link automatically; keep it.
- On route change, update `document.title` and move focus to the new page's
  `h1` (or `main`), as `RouteFocus` does. Do not move focus when only search
  params change.
- Provide a skip link to `main`. Restore scroll with `ScrollRestoration`.

## Hosting

- Single-page hosting needs a fallback that serves `index.html` for unknown paths
  while still returning real 404 status codes for missing static assets.
- If the app is served under a sub-path, set the router `basename` and Vite
  `base` to the same value.
- Cache `index.html` with revalidation and hashed assets as immutable, so new
  deployments are picked up and lazy route chunks stay resolvable.

## Anti-patterns

| Anti-pattern | Problem | Replacement |
| --- | --- | --- |
| Fetch in `useEffect` inside route components | waterfalls, flashes of empty state | loader plus query cache |
| `params.id!` passed straight to the API | crashes or requests for garbage ids | schema-validate params |
| One root error boundary only | whole layout disappears on any error | pathless boundary inside the layout |
| Guard component that renders `null` while checking auth | flicker, protected content flash | loader redirect before render |
| `navigate()` in render | loops and warnings | loader `redirect` or `<Navigate>` |
| `returnTo` used without validation | open redirect | `safeReturnTo` |
| `window.location.href = ...` for in-app links | full reload, state lost | `<Link>` / `navigate` |

## Acceptance gates

- [ ] Direct load, reload, and back/forward work for every new route.
- [ ] Params and search params are schema-validated; malformed values make no
      request.
- [ ] 401/403/404 and unexpected errors render distinct, focused boundaries with
      appropriate recovery.
- [ ] Title and focus update on navigation; filters do not steal focus.
- [ ] Redirects preserve a validated return path; tests cover open-redirect input.
- [ ] Hosting fallback and base path verified in a built preview, reported
      separately from memory-router tests.

## Sources

- React Router, route object: <https://reactrouter.com/start/data/route-object>
- React Router, data loading: <https://reactrouter.com/start/data/data-loading>
- React Router, error boundaries: <https://reactrouter.com/how-to/error-boundary>
- React Router, pending UI: <https://reactrouter.com/start/data/pending-ui>
- React Router, `createMemoryRouter` for testing: <https://reactrouter.com/api/data-routers/createMemoryRouter>
- TanStack Query, `QueryClient` (`ensureQueryData`): <https://tanstack.com/query/latest/docs/framework/react/reference/classes/QueryClient>
- Vite, `base` option: <https://vite.dev/config/shared-options.html#base>
- WAI-ARIA Authoring Practices, landmarks: <https://www.w3.org/WAI/ARIA/apg/practices/landmark-regions/>
- OWASP, unvalidated redirects: <https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html>
