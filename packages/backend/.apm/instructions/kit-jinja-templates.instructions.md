---
description: Apply to Jinja templates and template rendering configuration.
applyTo: "**/*.jinja,**/*.jinja2,**/*.j2,**/templates/**/*.html,**/templates/**/*.xml,**/templates/**/*.txt"
---

- Render HTML and XML with autoescaping enabled (`select_autoescape` or an equivalent environment setting); never disable it globally.
- Mark content safe (`|safe`, `Markup`) only for values the application produced and sanitized, never for user, model, or retrieved content.
- Never build a template from user-controlled text (`from_string`, `render_template_string`); untrusted templates need `SandboxedEnvironment` plus resource limits.
- Configure `StrictUndefined` or an equivalent so missing variables fail instead of rendering empty strings.
- Pass prepared, typed view data into templates; keep queries, I/O, and business decisions out of template logic.
- Keep templates small and composable with `extends`, `include`, and macros; avoid deep inheritance chains.
- Escape for the output context: HTML attributes, URLs, JavaScript, and CSS each need the matching encoder; use `tojson` to embed data in scripts.
- Load templates from a package or fixed directory through a loader; never resolve template names from request input without an allow list.
- Keep whitespace control (`trim_blocks`, `lstrip_blocks`) consistent across one environment.
- Test rendering with synthetic context, including hostile input escaping and missing-variable failures.
- Use the `kit-jinja` skill for environment setup and template review.
