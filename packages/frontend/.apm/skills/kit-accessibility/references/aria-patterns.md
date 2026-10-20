# ARIA patterns, focus, and announcements

## First rule of ARIA

Use a native HTML element with the needed semantics and behavior whenever one
exists. ARIA changes what assistive technology is told; it adds no keyboard
behavior, focus handling, or styling. Every ARIA role you add is a promise to
implement the matching interaction.

## Pattern selection

| Need | Native first | ARIA pattern if native does not fit |
| --- | --- | --- |
| Show and hide a section | `<details>` / `<summary>` | disclosure: button with `aria-expanded` and `aria-controls` |
| Modal task | `<dialog>` with `showModal()` | dialog (modal) pattern |
| Non-modal popup | `popover` attribute | non-modal dialog or menu, depending on content |
| Choose one of few options | radio group, `<select>` | radio group or listbox |
| Search with suggestions | `<input list>` with `<datalist>` for simple cases | combobox with listbox popup |
| Sections of one view | headings and links | tabs pattern ([template](../assets/tabs.tsx.template), [tests](../assets/tabs.test.tsx.template)) |
| Actions menu | buttons in a toolbar | menu button with menu |
| Data grid with cell navigation | `<table>` with interactive cells in normal tab order | grid pattern (only when spreadsheet-like navigation is required) |

## Composite widget keyboard model

- The widget is one tab stop; arrows move inside it (roving `tabindex` or
  `aria-activedescendant`).
- Home and End jump to the first and last item where the pattern lists them.
- Selection follows focus when panels are cheap to render (automatic
  activation); otherwise Enter or Space selects (manual activation).
- Typeahead (typing a character focuses the next matching item) is expected in
  listboxes, menus, and trees.

## Accessible names

Name computation order, simplified: `aria-labelledby`, then `aria-label`, then
native labelling (`<label>`, `alt`, `<legend>`, `<caption>`), then contents for
roles that take names from content (buttons, links), then `title`.

- Prefer visible labels; use `aria-label` only for icon-only controls.
- Keep the visible label at the start of the accessible name (Label in Name).
- Do not name generic containers (`div`, `span` without role); many screen
  readers ignore those names.
- Assert names in tests with `getByRole(role, { name })`; that exercises the
  same computation browsers use.

## Focus management rules

| Event | Focus goes to |
| --- | --- |
| Route change | new page `h1` (or `main`) |
| Modal opens | first meaningful control, or the dialog heading for long content |
| Modal closes | the element that opened it (if still present) |
| Item deleted from a list | next item, previous item, or the list heading |
| Inline edit saved | the control that started editing |
| Form submit failed | first invalid field or the error summary |
| Content loaded asynchronously | stays where it is; announce instead |

Never move focus on hover, on a timer, or when background data refreshes.

## Live regions

- Render live regions once, at load, and keep them mounted; regions inserted
  together with their text are often not announced. The
  [announcer](../assets/announcer.tsx.template) provides one polite and one
  assertive region for the app.
- `role="status"` (polite) for success, progress, and result counts;
  `role="alert"` (assertive) only for urgent errors that need immediate attention.
- Announce outcomes, not every intermediate step: "12 results" after a search
  settles, not each keystroke.
- Do not put a live role on a container whose content also receives focus; the
  content is announced twice.

## Hiding content

| Technique | Visible | Read by screen readers | Focusable |
| --- | --- | --- | --- |
| `hidden` / `display: none` | no | no | no |
| `.visually-hidden` utility | no | yes | yes, if focusable element |
| `aria-hidden="true"` | yes | no | still focusable: never on focusable content |
| `inert` attribute | yes (usually styled dimmed) | no | no |

## Component-level automated checks

The [axe helper](../assets/axe.ts.template) runs axe-core in component tests with
rules that need layout disabled (contrast, target size, page landmarks); run full
scans in a real browser for those.

## Acceptance gates

- [ ] Native elements used where available; each ARIA role has its full
      keyboard model implemented and tested.
- [ ] Focus destination defined and tested for every open, close, delete, and
      navigation event.
- [ ] Live regions persistent; announcements limited to outcomes.
- [ ] No `aria-hidden` on focusable content; inert used for background content.

## Sources

- WAI-ARIA Authoring Practices Guide: <https://www.w3.org/WAI/ARIA/apg/>
- APG, tabs pattern: <https://www.w3.org/WAI/ARIA/apg/patterns/tabs/>
- APG, keyboard interface practices: <https://www.w3.org/WAI/ARIA/apg/practices/keyboard-interface/>
- APG, naming and describing: <https://www.w3.org/WAI/ARIA/apg/practices/names-and-descriptions/>
- WAI-ARIA 1.2: <https://www.w3.org/TR/wai-aria-1.2/>
- Accessible Name and Description Computation 1.2: <https://www.w3.org/TR/accname-1.2/>
- Using ARIA (first rule): <https://www.w3.org/TR/using-aria/>
- MDN, ARIA live regions: <https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Guides/Live_regions>
- MDN, `inert`: <https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/inert>
- axe-core API: <https://github.com/dequelabs/axe-core/blob/develop/doc/API.md>
