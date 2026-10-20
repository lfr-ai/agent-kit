# Environment security: autoescape and the sandbox

## Choose the environment by output and trust

| Template source | Output | Environment |
| --- | --- | --- |
| Shipped with the application | HTML, XML, email HTML | `Environment` with autoescape on, `StrictUndefined` |
| Shipped with the application | Plain text, prompts, CLI output | `SandboxedEnvironment` or `Environment` with autoescape off, `StrictUndefined` |
| Supplied by users or tenants | Any | `ImmutableSandboxedEnvironment`, autoescape on, size and time limits |
| Generated SQL, shell, YAML | Do not template | Use parameterized APIs or structured serializers |

## Autoescape

- `Environment()` defaults to `autoescape=False`. Always set it explicitly.
- `select_autoescape(enabled_extensions=("html", "htm", "xml"))` enables escaping
  by template file extension. Set `default_for_string=True` so templates created
  with `from_string` are escaped too, and `default=True` when unknown extensions
  should be escaped.
- Escaping converts `& < > " '` to entities. It makes values safe inside HTML
  element content and quoted attribute values. It does **not** make values safe
  inside `<script>`, `<style>`, event handler attributes, unquoted attributes, or
  URLs:
  - For JavaScript data, use the `tojson` filter inside a `<script>` element of
    type `application/json` and read it with `JSON.parse`.
  - For URLs, build and validate them in code (allowed schemes only) and pass a
    finished string; `urlencode` encodes query parameters, not whole URLs.
  - For CSS, avoid interpolating user data.
- `|safe` and `Markup(...)` disable escaping for a value. Use them only on HTML
  produced by a trusted sanitizer in code, never on raw user input, and never
  wrap an f-string containing user values in `Markup`.
- `{% autoescape false %}` blocks should not exist in HTML templates.

## The sandbox

`jinja2.sandbox.SandboxedEnvironment` intercepts attribute and item access and
calls in templates:

- Attributes starting with an underscore and internal attributes of functions,
  methods, frames, and generators are blocked, which defeats the common
  `''.__class__.__mro__` escape.
- `range` is limited to a maximum length, and string formatting is routed
  through a sandboxed formatter.
- `ImmutableSandboxedEnvironment` additionally blocks methods that mutate
  built-in collections (`append`, `update`, `pop`, ...).
- Override `is_safe_attribute` or `is_safe_callable` to tighten further, for
  example to allow only attributes of specific view-model classes.

The sandbox constrains what template code can reach. It does not limit CPU,
memory, or output size, and it cannot protect objects you put in the context.
For user-supplied templates also:

- Cap template source length and rendered output length.
- Run rendering with a time budget (separate worker process with a timeout) when
  templates can loop over large data.
- Pass plain data (dicts, strings, numbers, frozen view models), never ORM
  sessions, clients, settings, or callables with side effects.
- Treat loader access as privileged: do not allow user templates to `include`
  or `extends` arbitrary names.

## Context hygiene

- Build a dedicated view model per template. Templates should not reach into
  services, repositories, or configuration.
- Do not register globals that expose the environment, the file system, or the
  settings object. Keep `env.globals` to small, pure helpers.
- Custom filters must be pure, deterministic, and escape-aware: return `Markup`
  only after escaping inputs with `markupsafe.escape`.

## Static review

Run [check_template_safety.py](../assets/check_template_safety.py) over source
and template directories. It flags missing autoescape, missing
`StrictUndefined`, direct `jinja2.Template(...)`, dynamic `Markup`,
`from_string` on variable text, `|safe`, disabled autoescape blocks, dunder
access, the `attr` filter, environment access, and variable include targets.
Reviewed exceptions carry `template-safety: reviewed` in a comment on the line.

## Sources

- <https://jinja.palletsprojects.com/en/stable/api/#autoescaping>
- <https://jinja.palletsprojects.com/en/stable/sandbox/>
- <https://jinja.palletsprojects.com/en/stable/templates/#html-escaping>
- <https://jinja.palletsprojects.com/en/stable/templates/#jinja-filters.tojson>
- <https://markupsafe.palletsprojects.com/en/stable/>
- <https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html>
