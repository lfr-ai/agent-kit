# URL state and history

## What belongs in the URL

| Put in the URL | Keep out of the URL |
| --- | --- |
| Selected record id (path segment) | Unsaved form drafts |
| Filters, sort, page, search text | Transient UI (hover, open tooltip) |
| Active tab or view mode that users share | Personal data, emails, tokens |
| Wizard step when steps are independently addressable | Large serialized state blobs |

Rule of thumb: if a colleague should see the same view from a pasted link, it is
URL state.

## Parsing

- Parse with a schema that uses `.catch(default)` per field so one bad value does
  not invalidate the rest; see [search-params.ts](../assets/search-params.ts.template).
- Treat numbers from the URL as strings until coerced and range-checked.
- Normalize on read (trim, lower-case enums if the API is case-insensitive) and
  serialize canonically on write: stable key order, defaults omitted, empty
  values dropped.
- Repeated keys (`?tag=a&tag=b`) need `getAll`; `Object.fromEntries` keeps only the
  last value, so use an explicit parser for array parameters.

## Push or replace

| Interaction | History |
| --- | --- |
| Typing in a search box, dragging a slider | replace (debounce the update) |
| Toggling a filter chip | replace, unless filters are a deliberate step users go back through |
| Pagination, opening a record, switching tabs that users treat as pages | push |
| Redirects after sign-in or form submission | replace |
| Normalizing an invalid URL to a canonical one | replace |

A Back press should undo one deliberate step, never a single keystroke.

## Paths and encoding

- Build paths with `encodeURIComponent` for every dynamic segment; ids can contain
  characters that change path meaning.
- Prefer stable opaque ids in paths over names that can change; add a readable
  slug only if the route tolerates slug changes (redirect to the canonical slug).
- Pick one trailing-slash policy and redirect the other form, so analytics and
  caches see one URL.
- Validate any URL taken from user input or query strings before navigating to
  it; only same-origin paths are safe destinations by default.

## Scroll and focus

- New page: scroll to top and focus the heading.
- Back/forward: restore the previous scroll position (router scroll
  restoration) and do not force focus to the top.
- Search-param change on the same page: keep scroll and focus where the user is;
  announce result counts politely if the list changes.

## Testing checklist

- Load each route directly with representative and malformed search params.
- Reload after changing filters; the same view returns.
- Navigate list, detail, Back: the list's filters, page, and scroll return.
- Type a filter, press Back once: the user leaves the page (replace worked) or
  returns to the previous deliberate step.
- Open a link in a new tab: it renders without in-memory state.

## Acceptance gates

- [ ] Shareable view state is in the URL and survives reload.
- [ ] Parsing never throws on hostile input; canonical serialization omits defaults.
- [ ] Push and replace choices follow the table above and are tested for Back.
- [ ] Dynamic segments are encoded; redirects use validated same-origin paths.

## Sources

- React Router, `useSearchParams`: <https://reactrouter.com/api/hooks/useSearchParams>
- React Router, `ScrollRestoration`: <https://reactrouter.com/api/components/ScrollRestoration>
- WHATWG URL Standard: <https://url.spec.whatwg.org/>
- MDN, History API: <https://developer.mozilla.org/en-US/docs/Web/API/History_API>
- MDN, `encodeURIComponent`: <https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/encodeURIComponent>
- Zod, `.catch()`: <https://zod.dev/api#catch>
