---
name: kit-routing
description: Use when adding routes, nested navigation, URL state, or route-level access behavior.
license: MIT
---

# Keep navigation addressable

## Resources

- [Navigation guide](references/guide.md): prerequisites, loop and cancellation
  recovery gates.
- [Route patterns](references/route-patterns.md): tree shape, loaders, actions,
  pending and error UI, access control, accessibility, hosting, anti-patterns.
- [URL state and history](references/url-state-and-history.md): what goes in the
  URL, parsing, push versus replace, encoding, scroll and focus.
- [Route and history contract](assets/route-contract.md) to fill per route.
- Templates: [router](assets/router.tsx.template),
  [route module with loader](assets/order-detail.route.tsx.template),
  [error boundary](assets/route-error-boundary.tsx.template),
  [title and focus](assets/route-focus.tsx.template),
  [search params](assets/search-params.ts.template),
  [memory-router tests](assets/router.test.tsx.template).

## Procedure

1. Read the guide; fill the route and history contract.
2. Inspect router version and mode, layout, existing boundaries, base path, and
   hosting fallback before registering a path.
3. Decide which state belongs in the URL so refresh, sharing, and history are
   predictable.
4. Validate params and search params with schemas before requests or rendering.
5. Load data in loaders through the query cache; avoid effect-driven fetches.
6. Define loading, not-found, denied, and failed states with focused boundaries.
7. Keep authorization on the server; client guards are navigation aids with a
   validated return path.
8. Use semantic links, `aria-current`, a skip link, title updates, and heading
   focus after navigation.
9. Choose push versus replace intentionally; test Back after each interaction.
10. Check canonical paths, encoding, trailing slashes, and redirect safety.
11. Test direct load, reload, invalid params, denial, retry, focus, and history
    with a memory router.
12. Report hosting and real-browser checks separately from router tests.

## Acceptance gates

- [ ] Direct load, reload, and back/forward work for every new route.
- [ ] Malformed params produce a 404 without a request.
- [ ] 401/403/404/unexpected failures render distinct focused boundaries.
- [ ] Return paths reject cross-origin destinations in tests.
- [ ] Title and focus update on navigation; filter changes keep focus.
