---
description: Add a route with validated params, loader-based data, loading, not-found, and denied states, URL-owned state, and tested history behavior.
argument-hint: The route path and purpose, e.g. "/invoices/:id detail page"
agent: agent
---

# Add a route

Make a new screen addressable: it loads correctly on direct visit, reload,
share, and Back, and fails in a defined way.

## Input

- The user-supplied argument gives the path and purpose. Ask which data it
  loads and who may see it if neighboring routes do not answer that.

## Procedure

1. Load [kit-routing](../skills/kit-routing/SKILL.md) and fill its route and
   history contract.
2. Inspect the router version and mode, layout nesting, base path, existing
   error boundaries, and how neighboring routes load data.
3. Decide which state belongs in the URL (filters, page, selected tab) so
   refresh, sharing, and history behave; keep transient state local.
4. Validate path and search params with a schema before any request or render;
   treat invalid values as not found or as a corrected redirect.
5. Load data in the route loader through the query cache from
   [kit-state-data](../skills/kit-state-data/SKILL.md), not in an effect.
6. Define loading, not-found, denied, and failed states with focused
   boundaries. Remember that client guards are navigation aids; the server
   enforces authorization.
7. Use semantic links, set `aria-current` for the active item, update the
   document title, and move focus to the main heading after navigation.
8. Choose push or replace deliberately for each navigation and test Back after
   each interaction.
9. Check encoding, trailing slashes, canonical paths, and that redirects only
   go to same-origin targets.
10. Write tests for direct load, reload, invalid params, denial, retry, focus,
    and history, then run type, lint, and test commands.

## Acceptance gates

- [ ] Direct load and reload render the same state as in-app navigation.
- [ ] Params are always validated before any request.
- [ ] Loading, not-found, denied, and failed states each have a test.
- [ ] Back returns to the previous meaningful state.

## Output

The route contract (path, params, search params, loader, states), files
changed, commands run with results, and hosting or real-browser checks still
needed.
