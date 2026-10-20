# React 19 patterns for feature code

Use these when the project actually runs React 19 or later; confirm the installed
version in the lockfile first. Older projects keep their existing idioms.

## Actions and pending state

An Action is an async function run inside a transition. React tracks its pending
state, keeps the current UI interactive, and commits the final state updates
together.

```tsx
const [isPending, startTransition] = useTransition();

function archive(orderId: string): void {
  startTransition(async () => {
    const result = await archiveOrder(orderId);
    if (!result.ok) {
      setError(result.message);
    }
  });
}
```

Decision rules:

- Server data mutation that other views read: prefer the query library's
  mutation (cache invalidation, retries, devtools). Use `useTransition` when the
  update is local or the project has no query layer.
- Form submission with a small return value (validation message, success flag):
  `useActionState` with `<form action={...}>`.
- Large forms with field-level validation, dirty tracking, and arrays: use the
  form library documented by `kit-forms`; do not reimplement it with actions.

## `useActionState`

```tsx
type RenameState = Readonly<{ error: string | null }>;

const [state, renameAction, isPending] = useActionState<RenameState, FormData>(
  async (_previous, formData) => {
    const name = String(formData.get("name") ?? "").trim();
    if (name.length === 0) {
      return { error: "Enter a name." };
    }
    const result = await renameDocument(documentId, name);
    return { error: result.ok ? null : result.message };
  },
  { error: null },
);
```

- The reducer receives the previous state; return a new object every time.
- Uncontrolled `<form action>` resets fields after a successful submit. When the
  user must keep their input after an error, return the submitted values in state
  and use them as `defaultValue`, or use a controlled form library.
- Associate the error with the field (`aria-describedby`, `aria-invalid`).

## `useOptimistic`

```tsx
const [optimisticItems, addOptimistic] = useOptimistic(
  items,
  (current: readonly Item[], pending: Item) => [...current, pending],
);
```

- Call the setter inside an Action or transition. React discards the optimistic
  value when the transition settles, so the source state must reflect the
  server's answer.
- Mark optimistic rows (for example "Saving…") so users do not act on them.
- When the query layer already supports optimistic updates with rollback, use
  one mechanism, not both.

## `use` and Suspense

- `use(promise)` suspends until the promise resolves. The promise must be
  created outside render (route loader, query cache, or a parent) and stay
  stable; creating it during render loops forever.
- `use(Context)` may be called conditionally, unlike `useContext`.
- Every Suspense boundary needs a fallback that preserves layout and an error
  boundary above it that offers recovery.

## Refs and context

- Function components accept `ref` as a normal prop in React 19; new primitives do
  not need `forwardRef`. Keep `forwardRef` where the project still supports
  React 18 consumers.
- `<Context value={...}>` renders a provider directly; `Context.Provider` remains
  valid during migration.
- Ref callbacks may return a cleanup function; use it for observers attached to
  the node instead of a separate effect.

## Effects

- Effects synchronize with external systems: subscriptions, timers, imperative
  widgets, document title. They are not for deriving values or reacting to user
  events.
- Strict Mode runs setup, cleanup, setup again in development. A correct effect
  produces the same observable result; fix leaks instead of guarding with a
  "has run" ref.
- Include every reactive value in the dependency list. If that causes loops, the
  logic belongs in an event handler or a derived value.

```tsx
useEffect(() => {
  const controller = new AbortController();
  const unsubscribe = presence.subscribe(documentId, setViewers, controller.signal);
  return () => {
    controller.abort();
    unsubscribe();
  };
}, [documentId]);
```

## Derived state and identity

| Need | Pattern |
| --- | --- |
| Value computed from props or state | compute during render; memoize only after measuring |
| Reset a subtree when an entity changes | `<Editor key={documentId} />` |
| Keep a draft while a list reorders | key by entity id, never index |
| Expensive pure computation | `useMemo` with a measured reason, or the React Compiler if adopted |
| Callback identity for a memoized child | `useCallback` only when the child is memoized |

If the project enables the React Compiler, do not hand-add memoization the
compiler already provides; follow its lint rules instead.

## Anti-patterns

| Anti-pattern | Symptom | Fix |
| --- | --- | --- |
| Effect that sets state from props | extra render, flicker, stale values | derive during render |
| Effect chain (A sets B, B sets C) | cascading renders, ordering bugs | compute in one event handler |
| Fetch in effect without abort | stale response overwrites newer input | query layer, or abort plus ignore flag |
| Promise created in render passed to `use` | infinite suspend loop | create in loader or cache |
| Disabling Strict Mode to stop double effects | hides missing cleanup | add cleanup |
| `useMemo` to fix a correctness bug | bug returns when memo invalidates | fix the data flow |

## Acceptance gates

- [ ] React version and rendering mode confirmed before choosing an API above.
- [ ] Each effect names its external system and has cleanup; the Strict Mode
      development cycle produces no duplicate subscriptions or requests.
- [ ] Optimistic UI is visibly marked and reverts on failure in a test.
- [ ] Form errors from actions are associated with their fields and announced.
- [ ] No derived value is stored in state.

## Sources

- React 19 release notes: <https://react.dev/blog/2024/12/05/react-19>
- `useActionState`: <https://react.dev/reference/react/useActionState>
- `useOptimistic`: <https://react.dev/reference/react/useOptimistic>
- `useTransition`: <https://react.dev/reference/react/useTransition>
- `use`: <https://react.dev/reference/react/use>
- You might not need an effect: <https://react.dev/learn/you-might-not-need-an-effect>
- Synchronizing with effects: <https://react.dev/learn/synchronizing-with-effects>
- Preserving and resetting state: <https://react.dev/learn/preserving-and-resetting-state>
- React Compiler: <https://react.dev/learn/react-compiler>
