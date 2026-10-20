# Undefined values, loading, and caching

## Undefined behavior

| Class | Missing variable renders as | Use |
| --- | --- | --- |
| `Undefined` (default) | Empty string; fails on most operations | Avoid in application templates |
| `ChainableUndefined` | Empty string, even through attribute chains | Rarely appropriate |
| `DebugUndefined` | The original `{{ name }}` text | Debugging only |
| `StrictUndefined` | Raises `UndefinedError` on any use | Application default |

With the default `Undefined`, a typo such as `{{ costumer_name }}` silently
renders nothing and ships an email that says "Hello ,". `StrictUndefined` turns
that into a test failure. Templates that legitimately accept optional values
test them explicitly (`{% if note is defined %}`) or receive `None` from the view
model and use `{{ note or "" }}`.

`StrictUndefined` also fails `{% if missing %}` and iteration over a missing
value, so tests catch absent context keys in every branch they exercise. Cover
each conditional branch with at least one test.

## Loaders

| Loader | Use |
| --- | --- |
| `PackageLoader("myapp", "templates")` | Templates shipped inside the installed package; works from wheels |
| `FileSystemLoader(paths)` | Templates in a configured directory; resolve the path from settings, never from user input |
| `DictLoader` | Tests and small embedded template sets |
| `ChoiceLoader` / `PrefixLoader` | Overrides (tenant branding) layered on defaults |

- `PackageLoader` resolves through the import system, so templates must be
  included as package data in the built wheel. Verify with an installed-artifact
  test, not only from the source checkout.
- Template names are trusted identifiers. Keep an allow-list of renderable
  names; never pass a request parameter to `get_template`. Jinja's file system
  loader rejects `..` segments, but an allow-list also prevents rendering
  internal partials directly.

## Caching

- The environment caches compiled templates in memory (`cache_size`, default
  400; `0` disables, `-1` means unbounded). Create one environment per process
  and reuse it; creating an environment per request discards the cache and
  recompiles every template.
- `auto_reload=True` (default) checks the source modification time on each
  `get_template`. Disable it in production where templates do not change, and
  keep it on in development.
- A bytecode cache (`FileSystemBytecodeCache`) persists compiled bytecode across
  process restarts. It helps large template sets with slow cold starts; store it
  in a private, writable directory.
- Compile every allow-listed template at startup or in CI to surface syntax
  errors before traffic does.

## Whitespace and output shape

- `trim_blocks=True` removes the first newline after a block tag and
  `lstrip_blocks=True` strips leading whitespace before block tags, which keeps
  generated text and email bodies tidy.
- `keep_trailing_newline=True` preserves the final newline of the template file,
  which matters for plain-text outputs compared byte-for-byte in tests.
- Use `{%-` and `-%}` for local whitespace control rather than reformatting the
  template.

## Async and native types

- `enable_async=True` allows `render_async` and awaiting async functions in
  templates. Only enable it if the consumer actually renders inside an event loop
  with async context values.
- `jinja2.nativetypes.NativeEnvironment` returns native Python values instead of
  strings. It is for configuration-like evaluation, not for HTML, and must not
  receive untrusted templates.

## Sources

- <https://jinja.palletsprojects.com/en/stable/api/#undefined-types>
- <https://jinja.palletsprojects.com/en/stable/api/#loaders>
- <https://jinja.palletsprojects.com/en/stable/api/#bytecode-cache>
- <https://jinja.palletsprojects.com/en/stable/api/#jinja2.Environment>
- <https://jinja.palletsprojects.com/en/stable/templates/#whitespace-control>
- <https://jinja.palletsprojects.com/en/stable/nativetypes/>
