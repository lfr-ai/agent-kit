---
name: kit-jinja
description: Use when authoring, reviewing, or rendering Jinja templates with data from outside the template.
license: MIT
---

# Keep template rendering safe and predictable

## Procedure

1. Identify the output context (HTML, email, plain text, prompt) and who authors the template source (shipped with the application or supplied by users). SQL, shell, and YAML are never rendered from templates; use parameterized or structured APIs.
2. Choose the environment from that pair; see [environment security](references/environment-security.md). Set `autoescape` explicitly (on for markup) and `undefined=StrictUndefined` everywhere.
3. Create one environment per process behind a `TemplateRenderer` port, starting from the [renderer template](assets/renderer.py.template). Load shipped templates with `PackageLoader` and keep an allow-list of renderable names.
4. For user-supplied templates use `ImmutableSandboxedEnvironment`, cap source and output size, and run with a time budget.
5. Build a dedicated view model for each template and pass only plain values. Never pass services, sessions, settings, secrets, or callables with side effects. Record required and optional keys in the [context manifest](assets/template_context.json.template).
6. Keep calculation and policy in typed application code; templates only format and branch on prepared values.
7. Escape per context: HTML escaping does not protect JavaScript, CSS, or URLs. Use `tojson` for script data and build URLs in code. Do not use `|safe` or `Markup` on unsanitized input.
8. Configure loading, caching, and whitespace deliberately; see [undefined, loading, and caching](references/undefined-loading-caching.md). Compile every allow-listed template at startup or in CI.
9. For prompt templates, separate instructions from delimited data, keep prompts versioned, and test exact output; see [prompt templates](references/prompt-templates.md).
10. Run [check_template_safety.py](assets/check_template_safety.py) over source and template directories. Fix findings or mark a reviewed exception with `template-safety: reviewed` in a comment on that line.
11. Adapt the [renderer tests](assets/test_renderer.py.template): expected output, escaping of metacharacters, missing values, unknown names, empty loops, sandbox escapes, and size limits.
12. Verify templates ship in the built package and render from the installed artifact.
13. Read the [template safety guide](references/guide.md) for failure modes and recovery.

## Acceptance gates

- Every environment sets `autoescape` explicitly and uses `StrictUndefined`; deliberate text-only environments carry a reviewed comment.
- Template names come from an allow-list; no request value selects a template or becomes template source outside a sandbox.
- Contexts contain only view-model values; no settings, secrets, clients, or environment access reach templates.
- The static checker reports no unreviewed findings.
- Tests cover escaping, missing values, each conditional branch, and (for user templates) sandbox and size limits.

## Commands

```text
python assets/check_template_safety.py src templates
python assets/check_template_safety.py --template-suffix .txt --template-suffix .j2 prompts
python assets/check_template_safety.py --self-test
pytest tests/unit/test_renderer.py -q
```
