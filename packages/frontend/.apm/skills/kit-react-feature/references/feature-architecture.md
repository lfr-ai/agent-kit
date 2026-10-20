# Feature folder architecture

A feature folder groups everything one user capability needs: its model, data
access, UI, and tests. The goal is local reasoning: a change to "orders" should be
reviewable by reading `src/features/orders/` plus the shared primitives it uses.

## Reference layout

```text
src/
  app/                    # composition root: providers, router, error shell
    providers.tsx
    router.tsx
  features/
    orders/
      index.ts            # public API; the only import target for other modules
      model/
        order.ts          # schemas, types, pure domain helpers
        order.test.ts
      api/
        orders.api.ts     # transport calls; parse responses with the model schemas
        orders.queries.ts # query key factory and queryOptions
        orders.queries.test.ts
      ui/
        order-list.tsx
        order-list.test.tsx
        order-form.tsx
      routes/
        orders.route.tsx  # route module: loader, element, error boundary
  shared/
    api/http-client.ts    # typed fetch wrapper, error types
    ui/                   # design-system primitives with no feature knowledge
    lib/                  # framework-free utilities
  config/runtime-config.ts
```

Copyable starting points:

- [Public index](../assets/index.ts.template)
- [Model with schema and pure helpers](../assets/order.model.ts.template)
- [List component covering every remote state](../assets/order-list.tsx.template)
  and its [behavior test](../assets/order-list.test.tsx.template)
- [Strict compiler settings](../assets/tsconfig.json.template) and
  [Vite build configuration](../assets/vite.config.ts.template)
- [Boundary checker](../assets/check_feature_imports.py) for import rules below

The query options file referenced by the list is described by the state and data
capability (`kit-state-data`); keep one definition per feature.

## Dependency rules

| From | May import | Must not import |
| --- | --- | --- |
| `app/` | any feature's `index.ts`, `shared/`, `config/` | feature internals |
| `features/a/**` | own internals, `shared/`, `config/`, other features' `index.ts` | other features' internals |
| `features/a/model/` | `shared/lib/`, schema library | React, router, query client, transport |
| `features/a/api/` | own `model/`, `shared/api/` | `ui/`, routes |
| `features/a/ui/` | own `model/`, `api/`, `shared/ui/` | transport primitives directly |
| `shared/**` | other `shared/**`, third-party packages | any `features/**` |

Run the checker in a consumer project to enforce the first and last rows:

```powershell
python check_feature_imports.py --root . --alias "@/=src/" --shared-dir src/shared
```

It prints `path:line: message` per violation and exits 1 when any exist. It reads
source text only; it does not replace the compiler, a bundler graph, or lint rules
the project already enforces.

## Decision guide: where does this code go?

1. Is it a validated shape or a pure rule about the domain (status labels, totals,
   permitted transitions)? Put it in `model/`; test it without React.
2. Does it call the network or another external system? Put it in `api/`, parse
   the response with the model schema, and expose it through query options.
3. Does it render or handle user events for one feature? Put it in `ui/`.
4. Does a second feature need it?
   - Needs the same behavior with feature meaning: export it from the owning
     feature's `index.ts`.
   - Needs a generic primitive without domain meaning: move it to `shared/` and
     remove the domain vocabulary first.
5. Is it application wiring (providers, routes, global error shell)? Put it in
   `app/`.

Do not create a `shared/` module for one caller "in case" another appears. Moving
code later is cheaper than maintaining a premature abstraction.

## Component shape

- Props are `Readonly<{...}>` object types; callbacks are named for the user
  intent (`onSelect`, `onSubmit`) rather than the DOM event.
- A component renders every state its data can be in. A query-backed view has a
  pending, error, empty, and success branch; background refresh uses
  `aria-busy` instead of replacing content with a spinner.
- Hooks are called unconditionally before early returns. Generate ids with
  `useId` so repeated instances stay unique.
- Keys come from stable entity ids, never array indexes for reorderable data.
- Text that needs translation goes through the project's localization layer; the
  templates use literal English only for brevity.

## Anti-patterns

| Anti-pattern | Why it fails | Replace with |
| --- | --- | --- |
| `useEffect(() => { fetch(...).then(setData) }, [id])` beside a query cache | races, no dedupe, no cache invalidation | query options consumed by `useQuery` or a route loader |
| Copying props into state "to edit them" | draft silently diverges from source; resets lost | explicit draft with a `key` reset or controlled form library |
| `index.ts` re-exporting every file with `export *` | the public API becomes the whole folder | named exports of the deliberate contract |
| Barrel imports from `@/features/orders/ui/...` in another feature | hidden coupling; refactors break callers | import from `@/features/orders` |
| `as Order` on a response | unvalidated data reaches UI and crashes later | `orderSchema.parse` in the API module |
| Spinner replaces content on every refetch | layout shift; focus loss | keep content, set `aria-busy`, show subtle progress |
| One component file with fetch, mapping, layout, and dialogs | untestable branches | split model, api, and ui by the rules above |

## Acceptance gates

- [ ] The feature exports a deliberate public API and the boundary checker (or an
      equivalent project rule) reports no violations.
- [ ] Model helpers have framework-free unit tests.
- [ ] Every query-backed view has pending, error-with-retry, empty, and success
      tests that go through the HTTP boundary, plus a malformed-payload test.
- [ ] Strict compiler settings pass with no new `any`, non-null assertions, or
      type assertions on transport data.
- [ ] Interactive elements are native controls or documented accessible
      primitives with visible labels.

## Sources

- React, Thinking in React: <https://react.dev/learn/thinking-in-react>
- React, Rules of Hooks: <https://react.dev/reference/rules/rules-of-hooks>
- React, `useId`: <https://react.dev/reference/react/useId>
- TypeScript, TSConfig reference: <https://www.typescriptlang.org/tsconfig/>
- Vite, configuration: <https://vite.dev/config/>
- TanStack Query, query options: <https://tanstack.com/query/latest/docs/framework/react/guides/query-options>
- Zod documentation: <https://zod.dev/>
