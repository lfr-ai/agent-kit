# Jinja template safety guide

## Purpose

Author and render Jinja templates that receive external data without leaking
secrets, enabling injection, or silently rendering incomplete output.

## Map of this skill

| Topic | Reference or asset |
| --- | --- |
| Autoescape, escaping contexts, sandbox | [environment security](environment-security.md) |
| `StrictUndefined`, loaders, caches, whitespace | [undefined, loading, and caching](undefined-loading-caching.md) |
| Language-model prompt assembly | [prompt templates](prompt-templates.md) |
| Renderer adapters | [renderer template](../assets/renderer.py.template) |
| Rendering tests | [renderer tests](../assets/test_renderer.py.template) |
| Context contract | [context manifest](../assets/template_context.json.template) |
| Static scan | [checker](../assets/check_template_safety.py) |

## Acceptance gates

- The environment has an explicit autoescape policy and `StrictUndefined`.
- Templates receive only the minimal, plain-data context they need.
- Templates pass the static scan, with each waiver justified in review.
- Shipped templates compile at startup or in CI and render from the installed
  package.

## Failure modes

- Templates that reach configuration, environment variables, or global
  application objects and print secrets.
- Server-side template injection: user text rendered as template source, or
  sandbox escapes through `__class__`, `__mro__`, `__subclasses__`, or `attr`.
- Cross-site scripting through `|safe`, `Markup` on formatted user text, or
  values placed in JavaScript, CSS, or URL contexts where HTML escaping does not
  apply.
- Missing variables rendering as empty strings under the default `Undefined`.
- Dynamic `include`/`extends` names allowing rendering of unintended templates.
- Per-request environment creation discarding the compile cache and adding
  latency.
- Templates missing from the built wheel because package data was not declared.

## Verification

- Run the static checker on Python sources and template directories.
- Render each template in unit tests with representative safe and hostile values
  (`<script>`, quotes, ampersands, delimiter strings, template syntax).
- Exercise every conditional branch at least once so `StrictUndefined` can catch
  missing keys.
- Review environment construction in code: autoescape, undefined, loader,
  `auto_reload`, and cache size.

## Recovery

- Replace unsafe templates with versions that accept typed view-model values.
- Remove environment, settings, and service references; pass values explicitly.
- Rotate any secret that a template may have rendered into output or logs.
- Add the failing input as a regression test before closing the issue.

## Scope and limits

The checker is a line- and syntax-level heuristic. It cannot prove that a custom
filter escapes correctly, that a context object is harmless, or that a sandbox
policy blocks every unsafe callable. Combine it with rendering tests and code
review.

## Sources

- <https://jinja.palletsprojects.com/en/stable/api/>
- <https://jinja.palletsprojects.com/en/stable/sandbox/>
- <https://jinja.palletsprojects.com/en/stable/templates/>
- <https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/07-Input_Validation_Testing/18-Testing_for_Server-side_Template_Injection>
